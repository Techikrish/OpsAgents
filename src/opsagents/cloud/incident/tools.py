"""Tools for the Incident Response Agent."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result, get_boto3_client

logger = logging.getLogger(__name__)


@tool
def get_active_alarms(profile: str = "", region: str = "us-east-1") -> str:
    """Get all CloudWatch alarms currently in ALARM state.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("cloudwatch", profile=profile or None, region=region)
        response = client.describe_alarms(StateValue="ALARM")

        alarms = []
        for alarm in response.get("MetricAlarms", []):
            alarms.append({
                "name": alarm["AlarmName"],
                "metric": alarm.get("MetricName", ""),
                "namespace": alarm.get("Namespace", ""),
                "state_reason": alarm.get("StateReason", "")[:200],
                "state_updated": str(alarm.get("StateUpdatedTimestamp", "")),
                "threshold": alarm.get("Threshold"),
                "comparison": alarm.get("ComparisonOperator", ""),
            })

        return format_tool_result("get_active_alarms", {
            "total_alarms": len(alarms),
            "alarms": alarms,
        })
    except Exception as e:
        return format_tool_result("get_active_alarms", {"error": str(e)})


@tool
def query_logs(
    log_group: str,
    query: str = "fields @timestamp, @message | filter @message like /ERROR|FATAL|Exception/ | sort @timestamp desc | limit 50",
    hours: int = 1,
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Query CloudWatch Logs using Logs Insights.

    Args:
        log_group: CloudWatch log group name.
        query: CloudWatch Logs Insights query string.
        hours: Number of hours to look back.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("logs", profile=profile or None, region=region)
        end_time = int(datetime.now(UTC).timestamp())
        start_time = end_time - (hours * 3600)

        response = client.start_query(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
            queryString=query,
        )
        query_id = response["queryId"]

        # Poll for results
        import time
        for _ in range(30):
            result = client.get_query_results(queryId=query_id)
            if result["status"] == "Complete":
                break
            time.sleep(1)

        records = []
        for row in result.get("results", [])[:50]:
            record = {field["field"]: field["value"] for field in row}
            records.append(record)

        return format_tool_result("query_logs", {
            "log_group": log_group,
            "period": f"Last {hours} hour(s)",
            "total_results": len(records),
            "results": records,
        })
    except Exception as e:
        return format_tool_result("query_logs", {"error": str(e)})


@tool
def analyze_metrics(
    namespace: str,
    metric_name: str,
    dimensions: str = "",
    hours: int = 3,
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Analyze CloudWatch metrics for anomalies and trends.

    Args:
        namespace: CloudWatch metric namespace (e.g., AWS/EC2, AWS/RDS).
        metric_name: Metric name (e.g., CPUUtilization).
        dimensions: JSON string of dimensions (e.g., '{"InstanceId": "i-123"}').
        hours: Number of hours to analyze.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        import json
        client = get_boto3_client("cloudwatch", profile=profile or None, region=region)
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)

        dim_list = []
        if dimensions:
            dim_dict = json.loads(dimensions)
            dim_list = [{"Name": k, "Value": v} for k, v in dim_dict.items()]

        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dim_list,
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5-minute intervals
            Statistics=["Average", "Maximum", "Minimum"],
        )

        datapoints = sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"])
        formatted = [
            {
                "timestamp": str(dp["Timestamp"]),
                "average": round(dp.get("Average", 0), 2),
                "maximum": round(dp.get("Maximum", 0), 2),
                "minimum": round(dp.get("Minimum", 0), 2),
            }
            for dp in datapoints
        ]

        # Simple anomaly detection
        if formatted:
            avgs = [dp["average"] for dp in formatted]
            mean = sum(avgs) / len(avgs)
            std = (sum((x - mean) ** 2 for x in avgs) / len(avgs)) ** 0.5
            anomalies = [dp for dp in formatted if abs(dp["average"] - mean) > 2 * std]
        else:
            mean = 0
            anomalies = []

        return format_tool_result("analyze_metrics", {
            "namespace": namespace,
            "metric": metric_name,
            "period": f"Last {hours}h",
            "datapoints": len(formatted),
            "average": round(mean, 2),
            "anomalies_detected": len(anomalies),
            "recent_values": formatted[-10:] if formatted else [],
        })
    except Exception as e:
        return format_tool_result("analyze_metrics", {"error": str(e)})


@tool
def get_recent_changes(hours: int = 24, profile: str = "", region: str = "us-east-1") -> str:
    """Get recent infrastructure changes from CloudTrail.

    Looks for resource creation, modification, and deletion events.

    Args:
        hours: Number of hours to look back.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("cloudtrail", profile=profile or None, region=region)
        start_time = datetime.now(UTC) - timedelta(hours=hours)

        # Look for write/modify events
        events = client.lookup_events(
            LookupAttributes=[{"AttributeKey": "ReadOnly", "AttributeValue": "false"}],
            StartTime=start_time,
            MaxResults=50,
        )

        changes = []
        for event in events.get("Events", []):
            changes.append({
                "event_name": event.get("EventName", ""),
                "event_time": str(event.get("EventTime", "")),
                "username": event.get("Username", ""),
                "source": event.get("EventSource", ""),
                "resources": [
                    {"type": r.get("ResourceType", ""), "name": r.get("ResourceName", "")}
                    for r in event.get("Resources", [])
                ],
            })

        return format_tool_result("get_recent_changes", {
            "period_hours": hours,
            "total_changes": len(changes),
            "changes": changes,
        })
    except Exception as e:
        return format_tool_result("get_recent_changes", {"error": str(e)})


@tool
def execute_runbook(
    runbook_name: str,
    parameters: str = "{}",
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Execute a predefined SSM Automation runbook for incident remediation.

    ⚠️ HIGH RISK: Executes remediation actions. Requires human approval.

    Args:
        runbook_name: Name of the SSM Automation document.
        parameters: JSON string of runbook parameters.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        import json
        client = get_boto3_client("ssm", profile=profile or None, region=region)
        params = json.loads(parameters) if isinstance(parameters, str) else parameters

        # Convert params to SSM format (list of strings)
        ssm_params = {k: [str(v)] if not isinstance(v, list) else v for k, v in params.items()}

        response = client.start_automation_execution(
            DocumentName=runbook_name,
            Parameters=ssm_params,
        )

        return format_tool_result("execute_runbook", {
            "execution_id": response["AutomationExecutionId"],
            "runbook": runbook_name,
            "status": "InProgress",
            "message": f"Runbook '{runbook_name}' execution started.",
        })
    except Exception as e:
        return format_tool_result("execute_runbook", {"error": str(e)})


@tool
def generate_postmortem(
    incident_summary: str,
    root_cause: str,
    actions_taken: str,
    impact: str = "",
) -> str:
    """Generate an incident post-mortem report template.

    Args:
        incident_summary: Brief summary of the incident.
        root_cause: Root cause analysis.
        actions_taken: Actions taken during incident response.
        impact: Customer/business impact description.
    """
    timestamp = datetime.now(UTC).isoformat()
    report = f"""# Incident Post-Mortem Report

**Date:** {timestamp}
**Status:** Draft

## Executive Summary
{incident_summary}

## Timeline
- **Detection:** [When was the issue first detected?]
- **Response:** [When did the team start responding?]
- **Mitigation:** [When was the issue mitigated?]
- **Resolution:** [When was the issue fully resolved?]

## Root Cause
{root_cause}

## Impact
{impact or '[Describe customer/business impact]'}

## Actions Taken
{actions_taken}

## Lessons Learned
- What went well?
- What could be improved?
- Where did we get lucky?

## Action Items
| # | Action | Owner | Deadline | Status |
|---|--------|-------|----------|--------|
| 1 | [Action item] | [Owner] | [Date] | TODO |
| 2 | [Action item] | [Owner] | [Date] | TODO |

## Prevention
- What changes will prevent this from recurring?
- What monitoring/alerting improvements are needed?
"""
    return format_tool_result("generate_postmortem", report)


def get_incident_tools() -> list:
    """Return all incident response tools."""
    return [
        get_active_alarms,
        query_logs,
        analyze_metrics,
        get_recent_changes,
        execute_runbook,
        generate_postmortem,
    ]
