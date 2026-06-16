"""Kubernetes Operations Agent.

Interacts with Kubernetes clusters to audit cluster status, troubleshoot failing
workloads, generate YAML manifests/Helm charts, and manage resources.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.devops.kubernetes.prompts import (
    MANIFEST_GENERATION_PROMPT,
    SYSTEM_PROMPT,
    TROUBLESHOOTING_PROMPT,
)
from opsagents.devops.kubernetes.tools import get_kubernetes_tools

logger = logging.getLogger(__name__)


class KubernetesAgent(BaseAgent):
    """Kubernetes Operations Agent.

    Capabilities:
    - Assess cluster health and query nodes/pods
    - Troubleshoot workload failures (OOM, CrashLoopBackOff)
    - Generate YAML manifests (Deployments, Services, etc.)
    - Scaffold Helm charts
    - Scale and rollback deployments
    - Analyze resource utilization
    """

    @property
    def name(self) -> str:
        return "Kubernetes Operations"

    @property
    def description(self) -> str:
        return (
            "Audits cluster status, troubleshoots workload failures, generates "
            "manifests and Helm charts, scales replicas, and optimizes resource requests."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_kubernetes_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the Kubernetes operation request."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this Kubernetes task and determine what steps to run:\n\n{task}\n\n"
            f"Determine:\n1. Operation category (status, troubleshoot, generate, scale, rollback, resource)\n"
            f"2. Scope (specific namespace, deployment, or pod name)\n"
            f"3. Potential risk level of requested operation (mutating vs read-only)"
        )
        return {
            "context": {
                "analysis": analysis,
                "task_type": self._classify_task(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create Kubernetes action plan."""
        context = state.get("context", {})
        task_type = context.get("task_type", "status")
        task = state["task"]

        actions: list[dict[str, Any]] = []
        if task_type == "troubleshoot":
            actions.append({
                "action": "Diagnose pod failure details",
                "resource": "Failing pod status & logs",
                "risk_level": "low",
                "type": "troubleshoot_run",
                "pod_name": self._extract_resource_name(task, "web-app"),
            })
        elif task_type == "generate":
            actions.append({
                "action": "Generate Kubernetes YAML manifests",
                "resource": "Workload specifications",
                "risk_level": "low",
                "type": "generate_manifests",
                "kind": self._determine_manifest_kind(task),
                "name": self._extract_resource_name(task, "my-app"),
            })
        elif task_type == "scale":
            actions.append({
                "action": "Scale Deployment replicas",
                "resource": "Deployment scaling settings",
                "risk_level": "medium",
                "type": "scale_run",
                "name": self._extract_resource_name(task, "web-app"),
                "replicas": self._extract_replicas(task),
            })
        elif task_type == "rollback":
            actions.append({
                "action": "Rollback Deployment to previous revision",
                "resource": "Deployment revision update",
                "risk_level": "high",
                "type": "rollback_run",
                "name": self._extract_resource_name(task, "web-app"),
            })
        elif task_type == "resource":
            actions.append({
                "action": "Analyze namespace resource allocations",
                "resource": "Pod metrics inventory",
                "risk_level": "low",
                "type": "resource_analysis",
            })
        else:
            # Default is get cluster status
            actions.append({
                "action": "Check Kubernetes cluster health status",
                "resource": "Nodes and system namespaces",
                "risk_level": "low",
                "type": "status_check",
            })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a Kubernetes agent action."""
        action_type = action.get("type", "")
        namespace = "default"  # Can be parsed or configured

        from opsagents.devops.kubernetes.tools import (
            analyze_resource_usage,
            generate_manifest,
            get_cluster_status,
            rollback_deployment,
            scale_deployment,
            troubleshoot_pod,
        )

        if action_type == "status_check":
            try:
                result = get_cluster_status.invoke({})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "troubleshoot_run":
            pod_name = action.get("pod_name", "web-app")
            try:
                result = troubleshoot_pod.invoke({"pod_name": pod_name, "namespace": namespace})

                # Analyze using LLM for recommendations
                try:
                    res_dict = json.loads(result)
                    res_data = res_dict.get("result", {})
                    diag_prompt = TROUBLESHOOTING_PROMPT.format(
                        namespace=namespace,
                        name=pod_name,
                        events=json.dumps(res_data.get("events", [])),
                        logs=res_data.get("logs", "")
                    )
                    diag_report = self.invoke_llm(diag_prompt)
                    output_data = f"{result}\n\nLLM Diagnoses:\n{diag_report}"
                except Exception:
                    output_data = str(result)

                return ActionResult(success=True, action=action["action"], output=output_data)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "generate_manifests":
            kind = action.get("kind", "Deployment")
            name = action.get("name", "my-app")
            try:
                prompt = MANIFEST_GENERATION_PROMPT.format(
                    requirements=state["task"],
                    context=f"Kind: {kind}, Name: {name}"
                )
                suggested_manifest = self.invoke_llm(prompt)

                result = generate_manifest.invoke({
                    "kind": kind,
                    "name": name,
                    "namespace": namespace
                })
                output_str = f"LLM Recommendations:\n{suggested_manifest}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "scale_run":
            name = action.get("name", "web-app")
            replicas = action.get("replicas", 3)
            try:
                result = scale_deployment.invoke({
                    "name": name,
                    "replicas": replicas,
                    "namespace": namespace
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "rollback_run":
            name = action.get("name", "web-app")
            try:
                result = rollback_deployment.invoke({
                    "name": name,
                    "namespace": namespace
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "resource_analysis":
            try:
                result = analyze_resource_usage.invoke({"namespace": namespace})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _classify_task(self, task: str) -> str:
        """Classify task type from description."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["troubleshoot", "fail", "crash", "oom", "debug", "error"]):
            return "troubleshoot"
        elif any(w in task_lower for w in ["generate", "manifest", "yaml", "helm", "chart"]):
            return "generate"
        elif any(w in task_lower for w in ["scale", "replica", "replicas", "increase", "decrease"]):
            return "scale"
        elif any(w in task_lower for w in ["rollback", "undo", "revert"]):
            return "rollback"
        elif any(w in task_lower for w in ["resource", "usage", "cpu", "memory", "request", "limit"]):
            return "resource"
        return "status"

    def _extract_resource_name(self, task: str, default: str) -> str:
        """Attempt to extract resource name from prompt."""
        # Simple extraction logic
        words = task.split()
        for i, word in enumerate(words):
            if word.lower() in ["pod", "deployment", "service", "workload"] and i + 1 < len(words):
                name = words[i + 1].strip("'\".,")
                if len(name) > 2:
                    return name
        return default

    def _determine_manifest_kind(self, task: str) -> str:
        """Determine what kind of manifest is being requested."""
        task_lower = task.lower()
        if "service" in task_lower:
            return "Service"
        elif "ingress" in task_lower:
            return "Ingress"
        elif "configmap" in task_lower:
            return "ConfigMap"
        return "Deployment"

    def _extract_replicas(self, task: str) -> int:
        """Extract replicas count if scaled."""
        for word in task.split():
            if word.isdigit():
                return int(word)
        return 3
