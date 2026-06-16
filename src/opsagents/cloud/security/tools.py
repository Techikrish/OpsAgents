"""Tools for the Security & Compliance Agent."""

from __future__ import annotations

import json
import logging
from datetime import UTC

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result, get_boto3_client

logger = logging.getLogger(__name__)


@tool
def scan_iam_policies(profile: str = "", region: str = "us-east-1") -> str:
    """Scan IAM policies for overly permissive access.

    Checks for wildcard actions, wildcard resources, and policies
    attached to users instead of roles.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("iam", profile=profile or None, region=region)
        findings = []

        # Get all IAM policies
        policies = client.list_policies(Scope="Local")["Policies"]
        for policy in policies[:50]:  # Limit to 50 policies
            arn = policy["Arn"]
            version = policy["DefaultVersionId"]
            try:
                doc = client.get_policy_version(
                    PolicyArn=arn, VersionId=version
                )["PolicyVersion"]["Document"]
                if isinstance(doc, str):
                    doc = json.loads(doc)

                for stmt in doc.get("Statement", []):
                    actions = stmt.get("Action", [])
                    if isinstance(actions, str):
                        actions = [actions]
                    resources = stmt.get("Resource", [])
                    if isinstance(resources, str):
                        resources = [resources]

                    if "*" in actions and stmt.get("Effect") == "Allow":
                        findings.append({
                            "severity": "CRITICAL",
                            "finding": "Wildcard action (*) in IAM policy",
                            "resource": arn,
                            "policy_name": policy["PolicyName"],
                            "remediation": "Replace * with specific actions needed.",
                        })
                    elif any("*" in a for a in actions) and stmt.get("Effect") == "Allow":
                        findings.append({
                            "severity": "HIGH",
                            "finding": "Broad wildcard actions in IAM policy",
                            "resource": arn,
                            "policy_name": policy["PolicyName"],
                            "actions": [a for a in actions if "*" in a],
                            "remediation": "Narrow down actions to least privilege.",
                        })
                    if "*" in resources and stmt.get("Effect") == "Allow":
                        findings.append({
                            "severity": "HIGH",
                            "finding": "Wildcard resource (*) in IAM policy",
                            "resource": arn,
                            "policy_name": policy["PolicyName"],
                            "remediation": "Specify exact resource ARNs.",
                        })
            except Exception:
                continue

        # Check for users with direct policy attachments
        users = client.list_users()["Users"]
        for user in users[:50]:
            attached = client.list_attached_user_policies(UserName=user["UserName"])
            if attached["AttachedPolicies"]:
                findings.append({
                    "severity": "MEDIUM",
                    "finding": "Policies attached directly to user",
                    "resource": user["UserName"],
                    "policies": [p["PolicyName"] for p in attached["AttachedPolicies"]],
                    "remediation": "Use IAM roles and groups instead of direct user policy attachments.",
                })

        return format_tool_result("scan_iam_policies", {
            "total_findings": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("scan_iam_policies", {"error": str(e)})


@tool
def scan_security_groups(profile: str = "", region: str = "us-east-1") -> str:
    """Scan EC2 security groups for open ports and unrestricted access.

    Checks for 0.0.0.0/0 ingress rules on sensitive ports.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("ec2", profile=profile or None, region=region)
        findings = []
        sensitive_ports = {22: "SSH", 3389: "RDP", 3306: "MySQL", 5432: "PostgreSQL",
                          27017: "MongoDB", 6379: "Redis", 9200: "Elasticsearch"}

        sgs = client.describe_security_groups()["SecurityGroups"]
        for sg in sgs:
            for perm in sg.get("IpPermissions", []):
                for ip_range in perm.get("IpRanges", []):
                    cidr = ip_range.get("CidrIp", "")
                    if cidr == "0.0.0.0/0":
                        from_port = perm.get("FromPort", 0)
                        to_port = perm.get("ToPort", 65535)
                        port_name = sensitive_ports.get(from_port, "")

                        if from_port == -1:  # All traffic
                            severity = "CRITICAL"
                            finding = "All traffic open to the internet"
                        elif from_port in sensitive_ports:
                            severity = "CRITICAL"
                            finding = f"Port {from_port} ({port_name}) open to the internet"
                        else:
                            severity = "HIGH"
                            finding = f"Port {from_port}-{to_port} open to the internet"

                        findings.append({
                            "severity": severity,
                            "finding": finding,
                            "resource": f"{sg['GroupId']} ({sg.get('GroupName', '')})",
                            "vpc_id": sg.get("VpcId", ""),
                            "remediation": "Restrict ingress to specific CIDR blocks or security groups.",
                        })

        return format_tool_result("scan_security_groups", {
            "total_security_groups": len(sgs),
            "total_findings": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("scan_security_groups", {"error": str(e)})


@tool
def scan_s3_buckets(profile: str = "", region: str = "us-east-1") -> str:
    """Scan S3 buckets for public access, encryption, and versioning issues.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        client = get_boto3_client("s3", profile=profile or None, region=region)
        findings = []
        buckets = client.list_buckets()["Buckets"]

        for bucket in buckets[:50]:
            name = bucket["Name"]

            # Check public access block
            try:
                pub = client.get_public_access_block(Bucket=name)["PublicAccessBlockConfiguration"]
                if not all([pub.get("BlockPublicAcls"), pub.get("IgnorePublicAcls"),
                           pub.get("BlockPublicPolicy"), pub.get("RestrictPublicBuckets")]):
                    findings.append({
                        "severity": "HIGH",
                        "finding": "S3 bucket public access block not fully enabled",
                        "resource": name,
                        "remediation": "Enable all public access block settings.",
                    })
            except client.exceptions.NoSuchPublicAccessBlockConfiguration:
                findings.append({
                    "severity": "CRITICAL",
                    "finding": "S3 bucket has no public access block configuration",
                    "resource": name,
                    "remediation": "Enable S3 Block Public Access for this bucket.",
                })
            except Exception:
                pass

            # Check encryption
            try:
                client.get_bucket_encryption(Bucket=name)
            except client.exceptions.ClientError:
                findings.append({
                    "severity": "HIGH",
                    "finding": "S3 bucket does not have default encryption",
                    "resource": name,
                    "remediation": "Enable default SSE-S3 or SSE-KMS encryption.",
                })

            # Check versioning
            try:
                ver = client.get_bucket_versioning(Bucket=name)
                if ver.get("Status") != "Enabled":
                    findings.append({
                        "severity": "MEDIUM",
                        "finding": "S3 bucket versioning not enabled",
                        "resource": name,
                        "remediation": "Enable versioning for data protection.",
                    })
            except Exception:
                pass

        return format_tool_result("scan_s3_buckets", {
            "total_buckets": len(buckets),
            "total_findings": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("scan_s3_buckets", {"error": str(e)})


@tool
def scan_cloudtrail(profile: str = "", region: str = "us-east-1", hours: int = 24) -> str:
    """Analyze CloudTrail logs for suspicious activity.

    Looks for root account usage, unauthorized API calls, and unusual patterns.

    Args:
        profile: AWS profile name.
        region: AWS region.
        hours: Number of hours to look back.
    """
    try:
        from datetime import datetime, timedelta

        client = get_boto3_client("cloudtrail", profile=profile or None, region=region)
        findings = []
        start_time = datetime.now(UTC) - timedelta(hours=hours)

        # Check for root account usage
        root_events = client.lookup_events(
            LookupAttributes=[{"AttributeKey": "Username", "AttributeValue": "root"}],
            StartTime=start_time,
            MaxResults=10,
        )
        if root_events.get("Events"):
            findings.append({
                "severity": "CRITICAL",
                "finding": f"Root account used {len(root_events['Events'])} times in last {hours}h",
                "events": [
                    {"event": e.get("EventName"), "time": str(e.get("EventTime"))}
                    for e in root_events["Events"][:5]
                ],
                "remediation": "Avoid using root account. Use IAM users/roles with MFA.",
            })

        # Check for access denied events
        denied_events = client.lookup_events(
            LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": "ConsoleLogin"}],
            StartTime=start_time,
            MaxResults=20,
        )
        failed_logins = [
            e for e in denied_events.get("Events", [])
            if "Failure" in str(e.get("CloudTrailEvent", ""))
        ]
        if len(failed_logins) > 3:
            findings.append({
                "severity": "HIGH",
                "finding": f"{len(failed_logins)} failed console logins in last {hours}h",
                "remediation": "Investigate potential brute force attacks. Enable MFA.",
            })

        return format_tool_result("scan_cloudtrail", {
            "period_hours": hours,
            "total_findings": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return format_tool_result("scan_cloudtrail", {"error": str(e)})


@tool
def check_cis_benchmark(profile: str = "", region: str = "us-east-1") -> str:
    """Check compliance against CIS AWS Foundations Benchmark key controls.

    Validates IAM, logging, monitoring, and networking controls.

    Args:
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        findings = []

        # CIS 1.x — IAM checks
        iam = get_boto3_client("iam", profile=profile or None, region=region)

        # CIS 1.4 — Root account MFA
        summary = iam.get_account_summary()["SummaryMap"]
        if not summary.get("AccountMFAEnabled"):
            findings.append({
                "control": "CIS 1.5",
                "severity": "CRITICAL",
                "finding": "Root account MFA is not enabled",
                "remediation": "Enable MFA on the root account immediately.",
            })

        # CIS 1.10 — Password policy
        try:
            policy = iam.get_account_password_policy()["PasswordPolicy"]
            if policy.get("MinimumPasswordLength", 0) < 14:
                findings.append({
                    "control": "CIS 1.8",
                    "severity": "MEDIUM",
                    "finding": f"Password minimum length is {policy.get('MinimumPasswordLength', 0)} (should be >= 14)",
                    "remediation": "Set minimum password length to 14 or greater.",
                })
        except Exception:
            findings.append({
                "control": "CIS 1.8",
                "severity": "HIGH",
                "finding": "No account password policy configured",
                "remediation": "Configure a strong password policy.",
            })

        # CIS 2.x — Logging checks
        ct = get_boto3_client("cloudtrail", profile=profile or None, region=region)
        trails = ct.describe_trails()["trailList"]
        if not trails:
            findings.append({
                "control": "CIS 3.1",
                "severity": "CRITICAL",
                "finding": "CloudTrail is not enabled",
                "remediation": "Enable CloudTrail with multi-region logging.",
            })

        return format_tool_result("check_cis_benchmark", {
            "benchmark": "CIS AWS Foundations Benchmark v1.5",
            "total_findings": len(findings),
            "findings": findings,
            "status": "PASS" if not findings else "FINDINGS_DETECTED",
        })
    except Exception as e:
        return format_tool_result("check_cis_benchmark", {"error": str(e)})


@tool
def generate_compliance_report(
    findings: str,
    framework: str = "CIS",
    output_format: str = "markdown",
) -> str:
    """Generate a formatted compliance report from scan findings.

    Args:
        findings: JSON string of scan findings.
        framework: Compliance framework (CIS, SOC2, PCI-DSS).
        output_format: Report format (markdown, json).
    """
    try:
        findings_data = json.loads(findings) if isinstance(findings, str) else findings
    except json.JSONDecodeError:
        findings_data = [{"finding": findings}]

    report_lines = [
        f"# {framework} Compliance Report",
        f"\n**Generated:** {__import__('datetime').datetime.now().isoformat()}",
        f"**Framework:** {framework}",
        f"**Total Findings:** {len(findings_data)}",
        "\n## Summary\n",
    ]

    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings_data:
        sev = f.get("severity", "MEDIUM")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    report_lines.append("| Severity | Count |")
    report_lines.append("|----------|-------|")
    for sev, count in severity_counts.items():
        report_lines.append(f"| {sev} | {count} |")

    report_lines.append("\n## Detailed Findings\n")
    for i, f in enumerate(findings_data, 1):
        report_lines.append(f"### {i}. {f.get('finding', 'Unknown')}")
        report_lines.append(f"- **Severity:** {f.get('severity', 'MEDIUM')}")
        if f.get("resource"):
            report_lines.append(f"- **Resource:** {f['resource']}")
        if f.get("control"):
            report_lines.append(f"- **Control:** {f['control']}")
        if f.get("remediation"):
            report_lines.append(f"- **Remediation:** {f['remediation']}")
        report_lines.append("")

    return format_tool_result("generate_compliance_report", "\n".join(report_lines))


@tool
def remediate_finding(
    finding_type: str,
    resource_id: str,
    remediation_action: str,
    profile: str = "",
    region: str = "us-east-1",
) -> str:
    """Apply a remediation fix for a specific security finding.

    ⚠️ HIGH RISK: This modifies AWS resources. Requires human approval.

    Args:
        finding_type: Type of finding (e.g., 's3_public_access', 'sg_open_port').
        resource_id: The resource to remediate.
        remediation_action: Specific action to take.
        profile: AWS profile name.
        region: AWS region.
    """
    try:
        if finding_type == "s3_public_access":
            client = get_boto3_client("s3", profile=profile or None, region=region)
            client.put_public_access_block(
                Bucket=resource_id,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
            return format_tool_result("remediate_finding", {
                "status": "remediated",
                "finding": finding_type,
                "resource": resource_id,
                "action": "Enabled all public access blocks",
            })

        elif finding_type == "s3_encryption":
            client = get_boto3_client("s3", profile=profile or None, region=region)
            client.put_bucket_encryption(
                Bucket=resource_id,
                ServerSideEncryptionConfiguration={
                    "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
                },
            )
            return format_tool_result("remediate_finding", {
                "status": "remediated",
                "finding": finding_type,
                "resource": resource_id,
                "action": "Enabled SSE-S3 default encryption",
            })

        else:
            return format_tool_result("remediate_finding", {
                "status": "unsupported",
                "finding": finding_type,
                "message": f"Automated remediation not available for '{finding_type}'. Manual remediation required.",
            })

    except Exception as e:
        return format_tool_result("remediate_finding", {"error": str(e)})


def get_security_tools() -> list:
    """Return all security & compliance tools."""
    return [
        scan_iam_policies,
        scan_security_groups,
        scan_s3_buckets,
        scan_cloudtrail,
        check_cis_benchmark,
        generate_compliance_report,
        remediate_finding,
    ]
