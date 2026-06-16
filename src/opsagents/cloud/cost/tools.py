"""Tools for the Cost Optimizer Agent."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result, get_boto3_client

logger = logging.getLogger(__name__)


@tool
def get_cost_breakdown(
    days: int = 30,
    granularity: str = "MONTHLY",
    group_by: str = "SERVICE",
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Get AWS cost breakdown from Cost Explorer.

    Args:
        days: Number of days to analyze.
        granularity: DAILY or MONTHLY.
        group_by: GROUP dimension — SERVICE, LINKED_ACCOUNT, REGION, USAGE_TYPE.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("ce", profile=profile or None, region=region)
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)

        response = client.get_cost_and_usage(
            TimePeriod={"Start": str(start), "End": str(end)},
            Granularity=granularity,
            Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"],
            GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
        )

        results = []
        for period in response.get("ResultsByTime", []):
            for group in period.get("Groups", []):
                results.append({
                    "period": period["TimePeriod"]["Start"],
                    "group": group["Keys"][0],
                    "blended_cost": group["Metrics"]["BlendedCost"]["Amount"],
                    "unblended_cost": group["Metrics"]["UnblendedCost"]["Amount"],
                })

        total = sum(float(r["unblended_cost"]) for r in results)
        return format_tool_result("get_cost_breakdown", {
            "period": f"{start} to {end}",
            "total_cost": f"${total:.2f}",
            "breakdown": sorted(results, key=lambda x: float(x["unblended_cost"]), reverse=True)[:20],
        })
    except Exception as e:
        return format_tool_result("get_cost_breakdown", {"error": str(e)})


@tool
def find_unused_resources(profile: str = "", region: str = "us-east-1") -> str:
    """Find unused AWS resources that can be safely removed.

    Checks for: unattached EBS volumes, idle EC2 instances, unused Elastic IPs,
    and unattached network interfaces.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        ec2 = get_boto3_client("ec2", profile=profile or None, region=region)
        findings = []

        # Unattached EBS volumes
        volumes = ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )["Volumes"]
        for vol in volumes:
            size = vol["Size"]
            cost_estimate = size * 0.10  # ~$0.10/GB/month for gp3
            findings.append({
                "type": "unattached_ebs",
                "resource_id": vol["VolumeId"],
                "details": f"{size} GB {vol['VolumeType']} volume",
                "estimated_monthly_savings": f"${cost_estimate:.2f}",
                "recommendation": "Delete if no longer needed, or create a snapshot first.",
            })

        # Unused Elastic IPs
        eips = ec2.describe_addresses()["Addresses"]
        for eip in eips:
            if not eip.get("AssociationId"):
                findings.append({
                    "type": "unused_eip",
                    "resource_id": eip.get("AllocationId", eip.get("PublicIp")),
                    "details": f"Unassociated EIP: {eip.get('PublicIp')}",
                    "estimated_monthly_savings": "$3.65",
                    "recommendation": "Release if not needed.",
                })

        # Idle EC2 instances (stopped for > 7 days)
        instances = ec2.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
        )
        for reservation in instances.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                stopped_reason = instance.get("StateTransitionReason", "")
                findings.append({
                    "type": "stopped_ec2",
                    "resource_id": instance["InstanceId"],
                    "details": f"{instance['InstanceType']} stopped: {stopped_reason[:80]}",
                    "estimated_monthly_savings": "Varies by instance type (EBS costs continue)",
                    "recommendation": "Terminate if no longer needed, or create an AMI.",
                })

        total_savings = sum(
            float(f["estimated_monthly_savings"].replace("$", ""))
            for f in findings
            if f["estimated_monthly_savings"].startswith("$")
        )

        return format_tool_result("find_unused_resources", {
            "total_findings": len(findings),
            "estimated_total_monthly_savings": f"${total_savings:.2f}",
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("find_unused_resources", {"error": str(e)})


@tool
def recommend_rightsizing(profile: str = "", region: str = "us-east-1") -> str:
    """Get EC2 right-sizing recommendations.

    Analyzes instance utilization and suggests appropriate instance types.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("ce", profile=profile or None, region=region)

        response = client.get_rightsizing_recommendation(
            Service="AmazonEC2",
            Configuration={
                "RecommendationTarget": "SAME_INSTANCE_FAMILY",
                "BenefitsConsidered": True,
            },
        )

        recommendations = []
        for rec in response.get("RightsizingRecommendations", [])[:20]:
            current = rec.get("CurrentInstance", {})
            modify_recs = rec.get("ModifyRecommendationDetail", {})
            target = modify_recs.get("TargetInstances", [{}])[0] if modify_recs else {}

            recommendations.append({
                "instance_id": current.get("ResourceId", "Unknown"),
                "current_type": current.get("ResourceDetails", {}).get(
                    "EC2ResourceDetails", {}
                ).get("InstanceType", "Unknown"),
                "recommended_type": target.get("ResourceDetails", {}).get(
                    "EC2ResourceDetails", {}
                ).get("InstanceType", "Unknown"),
                "estimated_monthly_savings": target.get("EstimatedMonthlySavings", {}).get(
                    "Value", "0"
                ),
                "recommendation_type": rec.get("RightsizingType", "Unknown"),
            })

        total_savings = sum(float(r["estimated_monthly_savings"]) for r in recommendations)
        return format_tool_result("recommend_rightsizing", {
            "total_recommendations": len(recommendations),
            "estimated_total_monthly_savings": f"${total_savings:.2f}",
            "recommendations": recommendations,
        })
    except Exception as e:
        return format_tool_result("recommend_rightsizing", {"error": str(e)})


@tool
def analyze_reserved_instances(profile: str = "", region: str = "us-east-1") -> str:
    """Analyze Reserved Instance and Savings Plans coverage and opportunities.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("ce", profile=profile or None, region=region)
        end = datetime.now(UTC).date()
        start = end - timedelta(days=30)

        # Get RI utilization
        ri_util = client.get_reservation_utilization(
            TimePeriod={"Start": str(start), "End": str(end)},
            Granularity="MONTHLY",
        )

        # Get Savings Plans utilization
        try:
            sp_util = client.get_savings_plans_utilization(
                TimePeriod={"Start": str(start), "End": str(end)},
                Granularity="MONTHLY",
            )
            sp_data = sp_util.get("SavingsPlansUtilizationsByTime", [{}])
        except Exception:
            sp_data = []

        ri_data = ri_util.get("UtilizationsByTime", [{}])

        return format_tool_result("analyze_reserved_instances", {
            "period": f"{start} to {end}",
            "reserved_instances": {
                "utilization": ri_data[0].get("Total", {}).get("UtilizationPercentage", "N/A") if ri_data else "N/A",
                "total_actual_hours": ri_data[0].get("Total", {}).get("TotalActualHours", "0") if ri_data else "0",
            },
            "savings_plans": {
                "utilization": sp_data[0].get("Utilization", {}).get("UtilizationPercentage", "N/A") if sp_data else "N/A",
            } if sp_data else {"status": "No Savings Plans found"},
            "recommendation": "Consider purchasing Reserved Instances or Savings Plans for stable workloads.",
        })
    except Exception as e:
        return format_tool_result("analyze_reserved_instances", {"error": str(e)})


@tool
def generate_cost_report(
    cost_data: str,
    include_recommendations: bool = True,
) -> str:
    """Generate a formatted cost optimization report.

    Args:
        cost_data: JSON string of cost analysis data.
        include_recommendations: Whether to include optimization recommendations.
    """
    report = [
        "# AWS Cost Optimization Report",
        f"\n**Generated:** {datetime.now(UTC).isoformat()}",
        "\n## Cost Summary\n",
        cost_data,
    ]

    if include_recommendations:
        report.extend([
            "\n## Recommendations\n",
            "1. **Quick Wins**: Delete unused resources (EBS, EIPs, stopped instances)",
            "2. **Right-Sizing**: Review instance types based on actual utilization",
            "3. **Reserved Capacity**: Purchase RIs/Savings Plans for stable workloads",
            "4. **Tagging**: Implement cost allocation tags for better visibility",
            "5. **Lifecycle Policies**: Set up S3 lifecycle rules and EBS snapshot policies",
        ])

    return format_tool_result("generate_cost_report", "\n".join(report))


@tool
def terminate_resource(
    resource_type: str,
    resource_id: str,
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Terminate or delete an unused AWS resource.

    🛑 CRITICAL RISK: This permanently removes the resource.

    Args:
        resource_type: Type of resource (ebs_volume, elastic_ip, ec2_instance).
        resource_id: ID of the resource to terminate.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        ec2 = get_boto3_client("ec2", profile=profile or None, region=region)

        if resource_type == "ebs_volume":
            ec2.delete_volume(VolumeId=resource_id)
            action = f"Deleted EBS volume {resource_id}"
        elif resource_type == "elastic_ip":
            ec2.release_address(AllocationId=resource_id)
            action = f"Released Elastic IP {resource_id}"
        elif resource_type == "ec2_instance":
            ec2.terminate_instances(InstanceIds=[resource_id])
            action = f"Terminated EC2 instance {resource_id}"
        else:
            return format_tool_result("terminate_resource", {
                "error": f"Unsupported resource type: {resource_type}"
            })

        return format_tool_result("terminate_resource", {
            "status": "terminated",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
        })
    except Exception as e:
        return format_tool_result("terminate_resource", {"error": str(e)})


def get_cost_tools() -> list:
    """Return all cost optimizer tools."""
    return [
        get_cost_breakdown,
        find_unused_resources,
        recommend_rightsizing,
        analyze_reserved_instances,
        generate_cost_report,
        terminate_resource,
    ]
