"""Tools for the Monitoring & Observability Agent."""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result

logger = logging.getLogger(__name__)


@tool
def setup_prometheus_rules(
    service_name: str,
    metric_name: str,
    threshold: float,
    duration: str = "5m",
) -> str:
    """Generate Prometheus alerting rules configuration for a service.

    Args:
        service_name: Name of the service.
        metric_name: Prometheus metric name.
        threshold: Alert threshold value.
        duration: Duration for threshold breach before firing.
    """
    rule_yaml = f"""groups:
  - name: {service_name}-alerts
    rules:
      - alert: High{service_name.title()}{metric_name.replace('_', '').title()}
        expr: {metric_name} > {threshold}
        for: {duration}
        labels:
          severity: critical
          service: {service_name}
        annotations:
          summary: "High {metric_name} on {service_name}"
          description: "Metric {metric_name} has exceeded {threshold} for more than {duration}."
"""
    return format_tool_result("setup_prometheus_rules", {
        "service": service_name,
        "yaml": rule_yaml
    })


@tool
def create_grafana_dashboard(dashboard_title: str, panel_queries: str) -> str:
    """Generate a standard Grafana dashboard JSON schema.

    Args:
        dashboard_title: Title of the Grafana dashboard.
        panel_queries: Comma-separated query strings for panels.
    """
    queries = [q.strip() for q in panel_queries.split(",")]
    panels = []
    for idx, query in enumerate(queries, 1):
        panels.append({
            "id": idx,
            "title": f"Panel {idx}: {query}",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": (idx - 1) % 2 * 12, "y": (idx - 1) // 2 * 8},
            "targets": [{"expr": query, "refId": f"Query_{idx}"}],
            "datasource": {"type": "prometheus", "uid": "prometheus-prod"}
        })

    dashboard = {
        "title": dashboard_title,
        "schemaVersion": 36,
        "uid": dashboard_title.lower().replace(" ", "-"),
        "panels": panels,
        "refresh": "5s"
    }

    return format_tool_result("create_grafana_dashboard", {
        "title": dashboard_title,
        "json": json.dumps(dashboard, indent=2)
    })


@tool
def setup_cloudwatch_alarms(
    metric_name: str,
    namespace: str,
    threshold: float,
    period: int = 300,
) -> str:
    """Generate AWS CloudWatch Alarm resource properties (CloudFormation syntax).

    Args:
        metric_name: Name of the metric.
        namespace: CloudWatch namespace.
        threshold: Alarm threshold.
        period: Period in seconds.
    """
    cfn_alarm = {
        "Type": "AWS::CloudWatch::Alarm",
        "Properties": {
            "AlarmName": f"High{metric_name}Alarm",
            "MetricName": metric_name,
            "Namespace": namespace,
            "Statistic": "Average",
            "Period": period,
            "EvaluationPeriods": 1,
            "Threshold": threshold,
            "ComparisonOperator": "GreaterThanThreshold",
            "AlarmActions": ["arn:aws:sns:us-east-1:123456789012:OperatorNotification"]
        }
    }
    return format_tool_result("setup_cloudwatch_alarms", {
        "metric": metric_name,
        "properties": cfn_alarm
    })


@tool
def define_slo(service: str, target: float) -> str:
    """Formulate SLI / SLO requirements and compute error budget metrics.

    Args:
        service: Service name.
        target: Target availability percent (e.g. 99.9).
    """
    budget = 100.0 - target
    monthly_downtime_secs = (30 * 24 * 3600) * (budget / 100.0)

    slo_details = {
        "service": service,
        "sli": f"Percentage of successful requests (HTTP 2xx/3xx/4xx responses) to '{service}' over 30 days.",
        "target_availability": f"{target}%",
        "monthly_error_budget": f"{budget}%",
        "max_allowable_downtime_monthly": f"{monthly_downtime_secs:.1f} seconds (~{monthly_downtime_secs/60:.1f} minutes)"
    }
    return format_tool_result("define_slo", slo_details)


@tool
def analyze_metrics_patterns(metrics_source: str) -> str:
    """Analyze high-level metrics telemetry for anomalies and suggest alarm thresholds.

    Args:
        metrics_source: Telemetry source metadata name.
    """
    anomalies = [
        {"metric": "http_requests_total", "time": "2026-06-16T10:00:00Z", "message": "Spike detected in HTTP 500 error counts"},
        {"metric": "jvm_memory_used_bytes", "time": "Steady rise", "message": "Potential memory leak detected"}
    ]
    return format_tool_result("analyze_metrics_patterns", {
        "source": metrics_source,
        "anomalies": anomalies,
        "recommended_alarm_thresholds": {
            "http_5xx_rate": "> 2%",
            "heap_utilization": "> 85%"
        }
    })


@tool
def generate_alerting_config(routing_key: str, receivers: str) -> str:
    """Generate Alertmanager routing and receiver configuration.

    Args:
        routing_key: Routing match field (e.g. team=ops).
        receivers: Comma-separated alert receivers (e.g. slack, pagerduty).
    """
    receiver_list = [r.strip() for r in receivers.split(",")]

    config = f"""route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  receiver: default-receiver
  routes:
    - match:
        {routing_key.replace('=', ': ')}
      receiver: custom-receiver-team

receivers:
  - name: default-receiver
    email_configs:
      - to: 'ops-alerts@example.com'
  - name: custom-receiver-team
"""
    for rec in receiver_list:
        if rec == "slack":
            config += """    slack_configs:
      - channel: '#ops-alerts'
        api_url: 'https://hooks.slack.com/services/T00/B00/X00'
"""
        elif rec == "pagerduty":
            config += """    pagerduty_configs:
      - service_key: 'PAGERDUTY_INTEGRATION_KEY'
"""

    return format_tool_result("generate_alerting_config", {
        "yaml": config
    })


def get_monitoring_tools() -> list:
    """Return all monitoring tools."""
    return [
        setup_prometheus_rules,
        create_grafana_dashboard,
        setup_cloudwatch_alarms,
        define_slo,
        analyze_metrics_patterns,
        generate_alerting_config
    ]
