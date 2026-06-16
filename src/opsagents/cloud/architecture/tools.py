"""Tools for the Architecture Review Agent."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result, get_boto3_client

logger = logging.getLogger(__name__)


@tool
def discover_resources(
    services: str = "ec2,s3,rds,lambda,ecs,elb",
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Discover and inventory AWS resources across services.

    Args:
        services: Comma-separated list of AWS services to discover.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        inventory: dict[str, list[dict[str, Any]]] = {}
        service_list = [s.strip().lower() for s in services.split(",")]

        if "ec2" in service_list:
            ec2 = get_boto3_client("ec2", profile=profile or None, region=region)
            instances = ec2.describe_instances()
            ec2_list = []
            for res in instances.get("Reservations", []):
                for inst in res.get("Instances", []):
                    name = next(
                        (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), ""
                    )
                    ec2_list.append({
                        "id": inst["InstanceId"],
                        "name": name,
                        "type": inst["InstanceType"],
                        "state": inst["State"]["Name"],
                        "az": inst.get("Placement", {}).get("AvailabilityZone", ""),
                        "vpc": inst.get("VpcId", ""),
                    })
            inventory["ec2"] = ec2_list

        if "s3" in service_list:
            s3 = get_boto3_client("s3", profile=profile or None, region=region)
            buckets = s3.list_buckets().get("Buckets", [])
            inventory["s3"] = [{"name": b["Name"], "created": str(b["CreationDate"])} for b in buckets]

        if "rds" in service_list:
            rds = get_boto3_client("rds", profile=profile or None, region=region)
            dbs = rds.describe_db_instances().get("DBInstances", [])
            inventory["rds"] = [
                {
                    "id": db["DBInstanceIdentifier"],
                    "engine": db["Engine"],
                    "class": db["DBInstanceClass"],
                    "status": db["DBInstanceStatus"],
                    "multi_az": db.get("MultiAZ", False),
                    "storage_encrypted": db.get("StorageEncrypted", False),
                }
                for db in dbs
            ]

        if "lambda" in service_list:
            lam = get_boto3_client("lambda", profile=profile or None, region=region)
            functions = lam.list_functions().get("Functions", [])
            inventory["lambda"] = [
                {
                    "name": f["FunctionName"],
                    "runtime": f.get("Runtime", ""),
                    "memory": f.get("MemorySize"),
                    "timeout": f.get("Timeout"),
                }
                for f in functions
            ]

        if "elb" in service_list:
            elbv2 = get_boto3_client("elbv2", profile=profile or None, region=region)
            lbs = elbv2.describe_load_balancers().get("LoadBalancers", [])
            inventory["elb"] = [
                {
                    "name": lb["LoadBalancerName"],
                    "type": lb["Type"],
                    "scheme": lb["Scheme"],
                    "state": lb["State"]["Code"],
                    "vpc": lb.get("VpcId", ""),
                }
                for lb in lbs
            ]

        total = sum(len(v) for v in inventory.values())
        return format_tool_result("discover_resources", {
            "total_resources": total,
            "region": region,
            "inventory": inventory,
        })
    except Exception as e:
        return format_tool_result("discover_resources", {"error": str(e)})


@tool
def check_reliability(profile: str = "", region: str = "us-east-1") -> str:
    """Check architecture reliability: multi-AZ, backups, auto-scaling.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        findings = []

        # Check RDS multi-AZ
        rds = get_boto3_client("rds", profile=profile or None, region=region)
        dbs = rds.describe_db_instances().get("DBInstances", [])
        for db in dbs:
            if not db.get("MultiAZ"):
                findings.append({
                    "pillar": "Reliability",
                    "severity": "HIGH",
                    "finding": f"RDS '{db['DBInstanceIdentifier']}' not Multi-AZ",
                    "recommendation": "Enable Multi-AZ for production databases.",
                })
            if not db.get("BackupRetentionPeriod"):
                findings.append({
                    "pillar": "Reliability",
                    "severity": "CRITICAL",
                    "finding": f"RDS '{db['DBInstanceIdentifier']}' has no automated backups",
                    "recommendation": "Enable automated backups with appropriate retention.",
                })

        # Check Auto Scaling Groups
        asg = get_boto3_client("autoscaling", profile=profile or None, region=region)
        groups = asg.describe_auto_scaling_groups().get("AutoScalingGroups", [])
        for group in groups:
            if group["MinSize"] == group["MaxSize"]:
                findings.append({
                    "pillar": "Reliability",
                    "severity": "MEDIUM",
                    "finding": f"ASG '{group['AutoScalingGroupName']}' has fixed capacity (min=max={group['MinSize']})",
                    "recommendation": "Consider dynamic scaling policies.",
                })
            azs = group.get("AvailabilityZones", [])
            if len(azs) < 2:
                findings.append({
                    "pillar": "Reliability",
                    "severity": "HIGH",
                    "finding": f"ASG '{group['AutoScalingGroupName']}' spans only {len(azs)} AZ(s)",
                    "recommendation": "Distribute across at least 2 AZs.",
                })

        return format_tool_result("check_reliability", {
            "total_findings": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("check_reliability", {"error": str(e)})


@tool
def check_performance(profile: str = "", region: str = "us-east-1") -> str:
    """Check architecture performance: instance types, caching, CDN.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        findings = []

        # Check for older generation instances
        ec2 = get_boto3_client("ec2", profile=profile or None, region=region)
        instances = ec2.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
        old_gen_prefixes = ["t2.", "m4.", "c4.", "r4.", "i3."]
        for res in instances.get("Reservations", []):
            for inst in res.get("Instances", []):
                itype = inst["InstanceType"]
                if any(itype.startswith(p) for p in old_gen_prefixes):
                    findings.append({
                        "pillar": "Performance",
                        "severity": "MEDIUM",
                        "finding": f"Instance {inst['InstanceId']} uses old-gen type {itype}",
                        "recommendation": "Upgrade to current generation for better price-performance.",
                    })

        # Check for CloudFront distributions
        try:
            cf = get_boto3_client("cloudfront", profile=profile or None, region=region)
            dists = cf.list_distributions().get("DistributionList", {}).get("Items", [])
            if not dists:
                findings.append({
                    "pillar": "Performance",
                    "severity": "LOW",
                    "finding": "No CloudFront distributions found",
                    "recommendation": "Consider using CloudFront CDN for static content.",
                })
        except Exception:
            pass

        # Check ElastiCache
        try:
            ec_client = get_boto3_client("elasticache", profile=profile or None, region=region)
            clusters = ec_client.describe_cache_clusters().get("CacheClusters", [])
            if not clusters:
                findings.append({
                    "pillar": "Performance",
                    "severity": "LOW",
                    "finding": "No ElastiCache clusters found",
                    "recommendation": "Consider caching for frequently accessed data.",
                })
        except Exception:
            pass

        return format_tool_result("check_performance", {
            "total_findings": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("check_performance", {"error": str(e)})


@tool
def generate_architecture_diagram(resources: str, description: str = "") -> str:
    """Generate a Mermaid architecture diagram from discovered resources.

    Args:
        resources: JSON string of discovered resources.
        description: Optional architecture description.
    """
    try:
        res_data = json.loads(resources) if isinstance(resources, str) else resources
    except json.JSONDecodeError:
        res_data = {}

    mermaid_lines = ["graph TB"]

    # Add subnets/groups based on resource types
    if "ec2" in res_data:
        mermaid_lines.append('    subgraph EC2["EC2 Instances"]')
        for inst in res_data["ec2"][:10]:
            name = inst.get("name", inst.get("id", "unknown"))
            safe_name = name.replace(" ", "_").replace("-", "_")[:20]
            mermaid_lines.append(f'        {safe_name}["{name}<br/>{inst.get("type", "")}"]')
        mermaid_lines.append("    end")

    if "rds" in res_data:
        mermaid_lines.append('    subgraph RDS["RDS Databases"]')
        for db in res_data["rds"][:10]:
            safe_id = db["id"].replace("-", "_")[:20]
            mermaid_lines.append(f'        {safe_id}["{db["id"]}<br/>{db.get("engine", "")}"]')
        mermaid_lines.append("    end")

    if "s3" in res_data:
        mermaid_lines.append('    subgraph S3["S3 Buckets"]')
        for bucket in res_data["s3"][:10]:
            safe_name = bucket["name"].replace("-", "_").replace(".", "_")[:20]
            mermaid_lines.append(f'        {safe_name}["{bucket["name"]}"]')
        mermaid_lines.append("    end")

    if "elb" in res_data:
        mermaid_lines.append('    subgraph ELB["Load Balancers"]')
        for lb in res_data["elb"][:5]:
            safe_name = lb["name"].replace("-", "_")[:20]
            mermaid_lines.append(f'        {safe_name}["{lb["name"]}<br/>{lb.get("type", "")}"]')
        mermaid_lines.append("    end")
        # Connect LB to EC2
        if "ec2" in res_data:
            mermaid_lines.append("    ELB --> EC2")

    if "ec2" in res_data and "rds" in res_data:
        mermaid_lines.append("    EC2 --> RDS")

    # Add user/internet entry point
    mermaid_lines.insert(1, '    Users["👥 Users"] --> ELB' if "elb" in res_data else '    Users["👥 Users"] --> EC2')

    diagram = "\n".join(mermaid_lines)
    return format_tool_result("generate_architecture_diagram", {
        "format": "mermaid",
        "diagram": diagram,
    })


@tool
def generate_review_report(findings: str, resources: str, diagram: str = "") -> str:
    """Generate a full Well-Architected review report.

    Args:
        findings: JSON string of all review findings.
        resources: JSON string of discovered resources.
        diagram: Optional Mermaid diagram string.
    """
    report = f"""# AWS Well-Architected Review Report

**Generated:** {__import__('datetime').datetime.now().isoformat()}

## Architecture Overview

{diagram if diagram else '[Architecture diagram pending]'}

## Resource Inventory Summary

{resources[:2000]}

## Findings Summary

{findings[:3000]}

## Next Steps

1. Address CRITICAL findings immediately
2. Plan HIGH severity remediations within 1-2 weeks
3. Include MEDIUM findings in next sprint
4. Track LOW findings as tech debt
"""
    return format_tool_result("generate_review_report", report)


def get_architecture_tools() -> list:
    """Return all architecture review tools."""
    return [
        discover_resources,
        check_reliability,
        check_performance,
        generate_architecture_diagram,
        generate_review_report,
    ]
