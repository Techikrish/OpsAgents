"""Base agent class — shared LangGraph foundation for all OpsAgents.

All 10 agents inherit from BaseAgent, which provides:
- Standard LangGraph state graph with the lifecycle:
  analyze → plan → human_approval → execute → report
- Built-in human-in-the-loop via LangGraph interrupt()
- LLM binding with tool calling
- Streaming support
- Error handling and retry logic
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from opsagents.core.approval import ApprovalHandler, create_approval_handler
from opsagents.core.llm_provider import get_llm_with_fallback
from opsagents.core.output import (
    print_action_plan,
    print_agent_header,
    print_report,
    print_status,
)
from opsagents.core.state import (
    ActionResult,
    AgentState,
    ApprovalRequest,
    RiskLevel,
    create_initial_state,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from opsagents.config import OpsAgentsConfig

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all OpsAgents.

    Subclasses must implement:
        - name: Agent display name
        - description: What the agent does
        - system_prompt: LLM system prompt
        - analyze(): Gather context and understand the task
        - plan(): Create an action plan
        - execute_action(): Execute a single approved action

    The base class handles:
        - LangGraph state graph construction
        - Human-in-the-loop approval flow
        - LLM interaction
        - Streaming output
        - Error handling
    """

    # ── Subclass must override ───────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent display name (e.g. 'Infrastructure Provisioner')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what this agent does."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for the LLM."""
        ...

    @abstractmethod
    def get_tools(self) -> list[Any]:
        """Return the list of LangChain tools this agent can use."""
        ...

    @abstractmethod
    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the task and gather context.

        Returns partial state update with 'context' and 'messages'.
        """
        ...

    @abstractmethod
    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create an action plan based on the analysis.

        Returns partial state update with 'action_plan'.
        """
        ...

    @abstractmethod
    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a single action from the plan.

        Args:
            state: Current agent state.
            action: The action dict from the action plan.

        Returns:
            ActionResult with success/failure info.
        """
        ...

    # ── Initialization ───────────────────────────────────────────────

    def __init__(
        self,
        config: OpsAgentsConfig,
        mode: str = "cli",
    ) -> None:
        """Initialize the base agent.

        Args:
            config: Full OpsAgents configuration.
            mode: "cli" for interactive terminal, "mcp" for MCP server.
        """
        self.config = config
        self.mode = mode

        # Create LLM instance
        self.llm: BaseChatModel = get_llm_with_fallback(config.llm)

        # Bind tools to LLM
        tools = self.get_tools()
        if tools:
            self.llm_with_tools = self.llm.bind_tools(tools)
        else:
            self.llm_with_tools = self.llm

        # Create approval handler
        self.approval_handler: ApprovalHandler = create_approval_handler(
            config.approval, mode=mode
        )

        # Build the LangGraph state graph
        self._graph = self._build_graph()

    # ── Graph Construction ───────────────────────────────────────────

    def _build_graph(self) -> Any:
        """Build the LangGraph state graph.

        Standard lifecycle:
            START → analyze → plan → approval_gate → execute → report → END
                                        ↓ (denied)
                                       END
        """
        graph = StateGraph(AgentState)

        # Add nodes
        graph.add_node("analyze", self._node_analyze)
        graph.add_node("plan", self._node_plan)
        graph.add_node("approval_gate", self._node_approval_gate)
        graph.add_node("execute", self._node_execute)
        graph.add_node("report", self._node_report)

        # Add edges
        graph.add_edge(START, "analyze")
        graph.add_edge("analyze", "plan")
        graph.add_edge("plan", "approval_gate")
        graph.add_conditional_edges(
            "approval_gate",
            self._route_after_approval,
            {"execute": "execute", "end": END},
        )
        graph.add_edge("execute", "report")
        graph.add_edge("report", END)

        # Compile with checkpointing for interrupt support
        memory = MemorySaver()
        return graph.compile(checkpointer=memory)

    # ── Graph Nodes ──────────────────────────────────────────────────

    def _node_analyze(self, state: AgentState) -> dict[str, Any]:
        """Node: Analyze the task and gather context."""
        if self.mode == "cli":
            print_status("Analyzing task...", "running")

        # Call subclass implementation
        updates = self.analyze(state)

        if self.mode == "cli":
            print_status("Analysis complete", "success")

        return updates

    def _node_plan(self, state: AgentState) -> dict[str, Any]:
        """Node: Create an action plan."""
        if self.mode == "cli":
            print_status("Creating action plan...", "running")

        # Call subclass implementation
        updates = self.create_plan(state)

        if self.mode == "cli" and updates.get("action_plan"):
            print_action_plan(updates["action_plan"])

        return updates

    def _node_approval_gate(self, state: AgentState) -> dict[str, Any]:
        """Node: Request human approval for the action plan.

        Uses LangGraph's interrupt() to pause execution and wait
        for human input.
        """
        action_plan = state.get("action_plan", [])
        if not action_plan:
            return {"approval_response": "approve"}

        # Determine the highest risk level in the plan
        risk_levels = [a.get("risk_level", "medium") for a in action_plan]
        risk_order = ["low", "medium", "high", "critical"]
        max_risk = max(risk_levels, key=lambda r: risk_order.index(r) if r in risk_order else 1)

        # Build approval request
        action_descriptions = "\n".join(
            f"  {i+1}. {a.get('action', 'Unknown')} → {a.get('resource', 'N/A')}"
            for i, a in enumerate(action_plan)
        )

        request = ApprovalRequest(
            action=f"Execute {len(action_plan)} action(s)",
            risk_level=RiskLevel(max_risk),
            details=f"The following actions will be performed:\n{action_descriptions}",
            estimated_impact=f"{len(action_plan)} resource(s) will be affected",
            rollback_plan="Actions can be reviewed individually. Destructive actions may not be reversible.",
        )

        if self.mode == "mcp":
            # In MCP mode, use LangGraph interrupt to pause and return
            response = interrupt(
                {
                    "type": "approval_required",
                    "request": request.model_dump(),
                    "message": (
                        f"🔐 Approval required for {len(action_plan)} action(s) "
                        f"(max risk: {max_risk.upper()}). "
                        f"Actions:\n{action_descriptions}"
                    ),
                }
            )
            return {"approval_response": response}
        else:
            # CLI mode — interactive prompt
            _approved, response = self.approval_handler.process(request)
            return {"approval_response": response}

    def _route_after_approval(self, state: AgentState) -> str:
        """Route after approval: execute or end."""
        response = state.get("approval_response", "deny")
        if response and response.lower() in ("approve", "auto-approved", "yes", "y"):
            return "execute"
        return "end"

    def _node_execute(self, state: AgentState) -> dict[str, Any]:
        """Node: Execute all approved actions."""
        if self.mode == "cli":
            print_status("Executing actions...", "running")

        action_plan = state.get("action_plan", [])
        results: list[ActionResult] = []

        for i, action in enumerate(action_plan, 1):
            action_name = action.get("action", f"Action {i}")
            if self.mode == "cli":
                print_status(f"[{i}/{len(action_plan)}] {action_name}", "running")

            try:
                result = self.execute_action(state, action)
                results.append(result)

                if self.mode == "cli":
                    status = "success" if result.success else "error"
                    msg = result.output[:80] if result.success else result.error[:80]
                    print_status(f"{action_name}: {msg}", status)

            except Exception as e:
                logger.error("Action '%s' failed: %s", action_name, e, exc_info=True)
                results.append(
                    ActionResult(
                        success=False,
                        action=action_name,
                        error=str(e),
                    )
                )
                if self.mode == "cli":
                    print_status(f"{action_name}: {e}", "error")

        return {"results": results}

    def _node_report(self, state: AgentState) -> dict[str, Any]:
        """Node: Generate a final report."""
        if self.mode == "cli":
            print_status("Generating report...", "running")

        report = self.generate_report(state)

        if self.mode == "cli":
            print_report(report)

        return {"final_report": report}

    # ── Report Generation (overridable) ──────────────────────────────

    def generate_report(self, state: AgentState) -> str:
        """Generate a final summary report.

        Subclasses can override this for custom report formats.
        Default implementation creates a markdown summary.
        """
        results = state.get("results", [])
        task = state.get("task", "Unknown task")

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        lines = [
            f"# {self.name} — Report",
            f"\n**Task:** {task}",
            f"\n**Results:** {succeeded} succeeded, {failed} failed",
            f"out of {len(results)} total actions.\n",
        ]

        if results:
            lines.append("## Action Details\n")
            for r in results:
                icon = "✅" if r.success else "❌"
                lines.append(f"- {icon} **{r.action}**")
                if r.success and r.output:
                    lines.append(f"  - {r.output[:200]}")
                elif r.error:
                    lines.append(f"  - Error: {r.error[:200]}")

        return "\n".join(lines)

    # ── LLM Helpers ──────────────────────────────────────────────────

    def invoke_llm(self, prompt: str, context: str = "") -> str:
        """Invoke the LLM with the agent's system prompt.

        Args:
            prompt: User message / task prompt.
            context: Additional context to include.

        Returns:
            LLM response text.
        """
        messages: list[AnyMessage] = [
            SystemMessage(content=self.system_prompt),
        ]
        if context:
            messages.append(HumanMessage(content=f"Context:\n{context}"))
        messages.append(HumanMessage(content=prompt))

        response = self.llm.invoke(messages)
        return response.content if isinstance(response.content, str) else str(response.content)

    def invoke_llm_with_tools(self, prompt: str, context: str = "") -> AIMessage:
        """Invoke the LLM with tools bound.

        Args:
            prompt: User message / task prompt.
            context: Additional context.

        Returns:
            AIMessage with potential tool calls.
        """
        messages: list[AnyMessage] = [
            SystemMessage(content=self.system_prompt),
        ]
        if context:
            messages.append(HumanMessage(content=f"Context:\n{context}"))
        messages.append(HumanMessage(content=prompt))

        return self.llm_with_tools.invoke(messages)

    # ── Public API ───────────────────────────────────────────────────

    def run(self, task: str, thread_id: str = "default") -> AgentState:
        """Run the agent on a task.

        Args:
            task: Natural language task description.
            thread_id: Thread ID for checkpointing (enables resume).

        Returns:
            Final agent state with results and report.
        """
        if self.mode == "cli":
            print_agent_header(self.name, task)

        initial_state = create_initial_state(task)

        config = {"configurable": {"thread_id": thread_id}}

        # Run the graph
        final_state = None
        for event in self._graph.stream(initial_state, config=config):
            # Capture the last state
            for _node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    if final_state is None:
                        final_state = {**initial_state, **node_output}
                    else:
                        final_state.update(node_output)

        return cast("AgentState", final_state or initial_state)

    def resume(self, thread_id: str, response: str) -> AgentState:
        """Resume a paused agent (after approval interrupt).

        Used in MCP mode to continue after the human responds
        to an approval request.

        Args:
            thread_id: Thread ID from the original run.
            response: Human's approval response.

        Returns:
            Updated agent state.
        """
        config = {"configurable": {"thread_id": thread_id}}

        final_state = None
        for event in self._graph.stream(Command(resume=response), config=config):
            for _node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    if final_state is None:
                        final_state = node_output
                    else:
                        final_state.update(node_output)

        return cast("AgentState", final_state or {})
