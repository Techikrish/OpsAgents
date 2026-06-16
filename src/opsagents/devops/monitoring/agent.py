"""Monitoring & Observability Agent.

Configures dashboard definitions, alerts thresholds, SLO error budgets, and routing
policies for application and cluster observability.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.devops.monitoring.prompts import (
    DASHBOARD_GENERATION_PROMPT,
    SLO_DEFINITION_PROMPT,
    SYSTEM_PROMPT,
)
from opsagents.devops.monitoring.tools import get_monitoring_tools

logger = logging.getLogger(__name__)


class MonitoringAgent(BaseAgent):
    """Monitoring & Observability Agent.

    Capabilities:
    - Generate Prometheus rules and Alertmanager layouts
    - Generate Grafana dashboard schemas
    - Establish AWS CloudWatch alarm specifications
    - Design SLIs / SLOs and measure error budget impact
    - Audit metrics trends for anomaly indicators
    """

    @property
    def name(self) -> str:
        return "Monitoring & Observability"

    @property
    def description(self) -> str:
        return (
            "Generates Grafana dashboards, Prometheus rules, CloudWatch alarms, "
            "configures Alertmanager routing, and defines SLI/SLO architectures."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_monitoring_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the monitoring setup request."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this monitoring task and determine what steps to run:\n\n{task}\n\n"
            f"Determine:\n1. Scope of work (dashboard creation, alert rules, SLO definition, routing)\n"
            f"2. Core metrics of interest\n"
            f"3. Monitoring system involved (Prometheus, Grafana, CloudWatch)"
        )
        return {
            "context": {
                "analysis": analysis,
                "task_type": self._classify_task(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create monitoring configuration plan."""
        context = state.get("context", {})
        task_type = context.get("task_type", "dashboard")
        state["task"]

        actions = []
        if task_type == "alerts":
            actions.append({
                "action": "Configure Prometheus alerting rules",
                "resource": "Prometheus rules config",
                "risk_level": "low",
                "type": "prometheus_rules",
                "service": "web-app",
                "metric": "http_requests_total",
                "threshold": 50.0,
            })
            actions.append({
                "action": "Generate alert routing definitions",
                "resource": "Alertmanager config",
                "risk_level": "low",
                "type": "alert_routing",
                "routing_key": "team=ops",
                "receivers": "slack,pagerduty",
            })
        elif task_type == "slo":
            actions.append({
                "action": "Define SLO & calculate error budget",
                "resource": "SLO document",
                "risk_level": "low",
                "type": "slo_calc",
                "service": "web-app",
                "target": 99.9,
            })
        elif task_type == "cloudwatch":
            actions.append({
                "action": "Generate CloudWatch Alarm definition",
                "resource": "AWS CloudWatch config",
                "risk_level": "low",
                "type": "cloudwatch_alarm",
                "metric": "CPUUtilization",
                "namespace": "AWS/EC2",
                "threshold": 80.0,
            })
        else:
            # Default is dashboard generation
            actions.append({
                "action": "Scan telemetry patterns",
                "resource": "Telemetry telemetry sources",
                "risk_level": "low",
                "type": "telemetry_scan",
            })
            actions.append({
                "action": "Create Grafana Dashboard json",
                "resource": "Grafana schema",
                "risk_level": "low",
                "type": "grafana_dashboard",
                "title": "Application Dashboard",
                "panel_queries": "sum(rate(http_requests_total[5m])), sum(container_memory_working_set_bytes)",
            })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a monitoring agent action."""
        action_type = action.get("type", "")

        from opsagents.devops.monitoring.tools import (
            analyze_metrics_patterns,
            create_grafana_dashboard,
            define_slo,
            generate_alerting_config,
            setup_cloudwatch_alarms,
            setup_prometheus_rules,
        )

        if action_type == "prometheus_rules":
            service = action.get("service", "web-app")
            metric = action.get("metric", "http_requests_total")
            threshold = action.get("threshold", 50.0)
            try:
                result = setup_prometheus_rules.invoke({
                    "service_name": service,
                    "metric_name": metric,
                    "threshold": threshold
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "alert_routing":
            key = action.get("routing_key", "team=ops")
            receivers = action.get("receivers", "slack")
            try:
                result = generate_alerting_config.invoke({
                    "routing_key": key,
                    "receivers": receivers
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "slo_calc":
            service = action.get("service", "web-app")
            target = action.get("target", 99.9)
            try:
                # Ask LLM to help refine requirements
                prompt = SLO_DEFINITION_PROMPT.format(
                    description=state["task"],
                    targets=f"Service: {service}, Availability Target: {target}%"
                )
                suggested_slo = self.invoke_llm(prompt)

                result = define_slo.invoke({"service": service, "target": target})
                output_str = f"LLM Recommendations:\n{suggested_slo}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "cloudwatch_alarm":
            metric = action.get("metric", "CPUUtilization")
            namespace = action.get("namespace", "AWS/EC2")
            threshold = action.get("threshold", 80.0)
            try:
                result = setup_cloudwatch_alarms.invoke({
                    "metric_name": metric,
                    "namespace": namespace,
                    "threshold": threshold
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "telemetry_scan":
            try:
                result = analyze_metrics_patterns.invoke({"metrics_source": "application_source"})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "grafana_dashboard":
            title = action.get("title", "App Dashboard")
            panel_queries = action.get("panel_queries", "up")
            try:
                prompt = DASHBOARD_GENERATION_PROMPT.format(
                    service=title,
                    metrics=panel_queries
                )
                suggested_dash = self.invoke_llm(prompt)

                result = create_grafana_dashboard.invoke({
                    "dashboard_title": title,
                    "panel_queries": panel_queries
                })
                output_str = f"LLM Recommendations:\n{suggested_dash}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _classify_task(self, task: str) -> str:
        """Classify task type based on description."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["alert", "threshold", "routing", "silence", "notification"]):
            return "alerts"
        elif any(w in task_lower for w in ["slo", "sli", "budget", "availability", "reliability target"]):
            return "slo"
        elif "cloudwatch" in task_lower:
            return "cloudwatch"
        return "dashboard"
