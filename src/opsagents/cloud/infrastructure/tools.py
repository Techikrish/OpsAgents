"""Tools for the Infrastructure Provisioner Agent.

Provides LangChain tools for Terraform and CloudFormation operations,
IaC code generation, cost estimation, and drift detection.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result, get_boto3_client, run_command

logger = logging.getLogger(__name__)


# ── Terraform Tools ──────────────────────────────────────────────────


@tool
def terraform_init(working_dir: str = ".") -> str:
    """Initialize a Terraform working directory.

    Downloads providers and modules, configures the backend.

    Args:
        working_dir: Path to the Terraform project directory.
    """
    result = run_command(["terraform", "init", "-no-color"], cwd=working_dir)
    return format_tool_result("terraform_init", result)


@tool
def terraform_plan(working_dir: str = ".", var_file: str = "") -> str:
    """Create a Terraform execution plan showing what changes will be made.

    This is a read-only operation — no resources are modified.

    Args:
        working_dir: Path to the Terraform project directory.
        var_file: Optional path to a .tfvars file.
    """
    cmd = ["terraform", "plan", "-no-color", "-detailed-exitcode"]
    if var_file:
        cmd.extend(["-var-file", var_file])

    result = run_command(cmd, cwd=working_dir)
    return format_tool_result("terraform_plan", result)


@tool
def terraform_apply(working_dir: str = ".", var_file: str = "", auto_approve: bool = False) -> str:
    """Apply Terraform changes to create/update infrastructure.

    ⚠️ HIGH RISK: This modifies real infrastructure. Requires human approval.

    Args:
        working_dir: Path to the Terraform project directory.
        var_file: Optional path to a .tfvars file.
        auto_approve: If True, skip interactive approval (use with caution).
    """
    cmd = ["terraform", "apply", "-no-color"]
    if auto_approve:
        cmd.append("-auto-approve")
    if var_file:
        cmd.extend(["-var-file", var_file])

    result = run_command(cmd, cwd=working_dir, timeout=600)
    return format_tool_result("terraform_apply", result)


@tool
def terraform_destroy(working_dir: str = ".", auto_approve: bool = False) -> str:
    """Destroy all Terraform-managed infrastructure.

    🛑 CRITICAL RISK: This permanently destroys resources. Requires explicit confirmation.

    Args:
        working_dir: Path to the Terraform project directory.
        auto_approve: If True, skip interactive approval (use with extreme caution).
    """
    cmd = ["terraform", "destroy", "-no-color"]
    if auto_approve:
        cmd.append("-auto-approve")

    result = run_command(cmd, cwd=working_dir, timeout=600)
    return format_tool_result("terraform_destroy", result)


@tool
def terraform_validate(working_dir: str = ".") -> str:
    """Validate Terraform configuration files for syntax errors.

    This is a read-only operation.

    Args:
        working_dir: Path to the Terraform project directory.
    """
    result = run_command(["terraform", "validate", "-no-color", "-json"], cwd=working_dir)
    return format_tool_result("terraform_validate", result)


@tool
def terraform_show_state(working_dir: str = ".") -> str:
    """Show the current Terraform state (managed resources).

    This is a read-only operation.

    Args:
        working_dir: Path to the Terraform project directory.
    """
    result = run_command(["terraform", "show", "-no-color", "-json"], cwd=working_dir)
    return format_tool_result("terraform_show_state", result)


# ── CloudFormation Tools ─────────────────────────────────────────────


@tool
def cfn_validate(template_path: str, region: str = "us-east-1") -> str:
    """Validate a CloudFormation template.

    This is a read-only operation that checks template syntax.

    Args:
        template_path: Path to the CloudFormation template file.
        region: AWS region for validation.
    """
    try:
        client = get_boto3_client("cloudformation", region=region)
        with open(template_path) as f:
            template_body = f.read()

        response = client.validate_template(TemplateBody=template_body)
        return format_tool_result(
            "cfn_validate",
            {
                "valid": True,
                "parameters": [p["ParameterKey"] for p in response.get("Parameters", [])],
                "capabilities": response.get("Capabilities", []),
                "description": response.get("Description", ""),
            },
            summary="Template is valid.",
        )
    except Exception as e:
        return format_tool_result("cfn_validate", {"valid": False, "error": str(e)})


@tool
def cfn_create_stack(
    stack_name: str,
    template_path: str,
    parameters: dict[str, str] | None = None,
    region: str = "us-east-1",
) -> str:
    """Create a new CloudFormation stack.

    ⚠️ HIGH RISK: This creates real AWS resources. Requires human approval.

    Args:
        stack_name: Name for the CloudFormation stack.
        template_path: Path to the template file.
        parameters: Stack parameter key-value pairs.
        region: AWS region.
    """
    try:
        client = get_boto3_client("cloudformation", region=region)
        with open(template_path) as f:
            template_body = f.read()

        kwargs: dict[str, Any] = {
            "StackName": stack_name,
            "TemplateBody": template_body,
            "Capabilities": ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
        }

        if parameters:
            kwargs["Parameters"] = [
                {"ParameterKey": k, "ParameterValue": v}
                for k, v in parameters.items()
            ]

        response = client.create_stack(**kwargs)
        return format_tool_result(
            "cfn_create_stack",
            {"stack_id": response["StackId"], "status": "CREATE_IN_PROGRESS"},
            summary=f"Stack '{stack_name}' creation initiated.",
        )
    except Exception as e:
        return format_tool_result("cfn_create_stack", {"error": str(e)})


@tool
def cfn_update_stack(
    stack_name: str,
    template_path: str,
    parameters: dict[str, str] | None = None,
    region: str = "us-east-1",
) -> str:
    """Update an existing CloudFormation stack.

    ⚠️ HIGH RISK: This modifies existing infrastructure. Requires human approval.

    Args:
        stack_name: Name of the existing stack.
        template_path: Path to the updated template file.
        parameters: Updated parameter key-value pairs.
        region: AWS region.
    """
    try:
        client = get_boto3_client("cloudformation", region=region)
        with open(template_path) as f:
            template_body = f.read()

        kwargs: dict[str, Any] = {
            "StackName": stack_name,
            "TemplateBody": template_body,
            "Capabilities": ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
        }

        if parameters:
            kwargs["Parameters"] = [
                {"ParameterKey": k, "ParameterValue": v}
                for k, v in parameters.items()
            ]

        client.update_stack(**kwargs)
        return format_tool_result(
            "cfn_update_stack",
            {"status": "UPDATE_IN_PROGRESS"},
            summary=f"Stack '{stack_name}' update initiated.",
        )
    except Exception as e:
        return format_tool_result("cfn_update_stack", {"error": str(e)})


@tool
def cfn_delete_stack(stack_name: str, region: str = "us-east-1") -> str:
    """Delete a CloudFormation stack and all its resources.

    🛑 CRITICAL RISK: This permanently destroys all stack resources.

    Args:
        stack_name: Name of the stack to delete.
        region: AWS region.
    """
    try:
        client = get_boto3_client("cloudformation", region=region)
        client.delete_stack(StackName=stack_name)
        return format_tool_result(
            "cfn_delete_stack",
            {"status": "DELETE_IN_PROGRESS"},
            summary=f"Stack '{stack_name}' deletion initiated.",
        )
    except Exception as e:
        return format_tool_result("cfn_delete_stack", {"error": str(e)})


@tool
def cfn_describe_stack(stack_name: str, region: str = "us-east-1") -> str:
    """Describe a CloudFormation stack's current status and outputs.

    This is a read-only operation.

    Args:
        stack_name: Name of the stack.
        region: AWS region.
    """
    try:
        client = get_boto3_client("cloudformation", region=region)
        response = client.describe_stacks(StackName=stack_name)
        stacks = response.get("Stacks", [])
        if not stacks:
            return format_tool_result("cfn_describe_stack", {"error": "Stack not found"})

        stack = stacks[0]
        return format_tool_result(
            "cfn_describe_stack",
            {
                "stack_name": stack["StackName"],
                "status": stack["StackStatus"],
                "created": str(stack.get("CreationTime", "")),
                "updated": str(stack.get("LastUpdatedTime", "")),
                "outputs": {
                    o["OutputKey"]: o["OutputValue"]
                    for o in stack.get("Outputs", [])
                },
                "parameters": {
                    p["ParameterKey"]: p["ParameterValue"]
                    for p in stack.get("Parameters", [])
                },
            },
        )
    except Exception as e:
        return format_tool_result("cfn_describe_stack", {"error": str(e)})


# ── Cost Estimation ──────────────────────────────────────────────────


@tool
def estimate_cost(resource_type: str, configuration: str, region: str = "us-east-1") -> str:
    """Estimate monthly AWS cost for a resource configuration.

    Provides approximate cost estimates based on AWS pricing.

    Args:
        resource_type: AWS resource type (e.g., "ec2", "rds", "s3").
        configuration: Description of the resource configuration.
        region: AWS region for pricing.
    """
    # Cost estimation lookup tables (approximate monthly costs)
    cost_estimates: dict[str, dict[str, float]] = {
        "ec2": {
            "t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37,
            "t3.large": 60.74, "m5.large": 69.12, "m5.xlarge": 138.24,
            "c5.large": 61.20, "r5.large": 90.72,
        },
        "rds": {
            "db.t3.micro": 12.41, "db.t3.small": 24.82, "db.t3.medium": 49.64,
            "db.m5.large": 124.10, "db.r5.large": 172.80,
        },
        "s3": {"standard_per_gb": 0.023, "ia_per_gb": 0.0125},
        "nat_gateway": {"per_gateway": 32.40, "per_gb_processed": 0.045},
        "alb": {"per_alb": 16.20, "per_lcu_hour": 5.84},
    }

    resource_lower = resource_type.lower()
    config_lower = configuration.lower()

    estimate_info = {"resource_type": resource_type, "configuration": configuration, "region": region}

    if resource_lower in cost_estimates:
        prices = cost_estimates[resource_lower]
        for key, price in prices.items():
            if key in config_lower:
                estimate_info["estimated_monthly_cost"] = f"${price:.2f}"
                estimate_info["pricing_key"] = key
                break
        else:
            estimate_info["note"] = "Exact configuration not found in lookup table. Prices are approximate."
            if prices:
                sum(prices.values()) / len(prices)
                estimate_info["average_range"] = f"${min(prices.values()):.2f} - ${max(prices.values()):.2f}/month"
    else:
        estimate_info["note"] = "Resource type not in local pricing database. Check AWS Pricing Calculator."

    return format_tool_result("estimate_cost", estimate_info)


# ── Drift Detection ──────────────────────────────────────────────────


@tool
def detect_drift(stack_name: str = "", working_dir: str = ".", iac_tool: str = "terraform") -> str:
    """Detect drift between actual infrastructure and IaC definitions.

    Compares the current state of resources against what's defined in code.

    Args:
        stack_name: CloudFormation stack name (if using CFN).
        working_dir: Terraform working directory (if using Terraform).
        iac_tool: IaC tool to use — 'terraform' or 'cloudformation'.
    """
    if iac_tool == "terraform":
        # Terraform drift detection via plan
        result = run_command(
            ["terraform", "plan", "-no-color", "-detailed-exitcode"],
            cwd=working_dir,
        )
        has_drift = result["returncode"] == 2
        return format_tool_result(
            "detect_drift",
            {
                "tool": "terraform",
                "drift_detected": has_drift,
                "details": result["stdout"] if has_drift else "No drift detected.",
            },
        )
    else:
        # CloudFormation drift detection
        try:
            client = get_boto3_client("cloudformation")
            response = client.detect_stack_drift(StackName=stack_name)
            drift_id = response["StackDriftDetectionId"]

            # Get drift results
            import time
            for _ in range(30):
                status = client.describe_stack_drift_detection_status(
                    StackDriftDetectionId=drift_id
                )
                if status["DetectionStatus"] == "DETECTION_COMPLETE":
                    break
                time.sleep(2)

            drifted = client.describe_stack_resource_drifts(
                StackName=stack_name,
                StackResourceDriftStatusFilters=["MODIFIED", "DELETED"],
            )

            return format_tool_result(
                "detect_drift",
                {
                    "tool": "cloudformation",
                    "stack": stack_name,
                    "drift_status": status.get("StackDriftStatus", "UNKNOWN"),
                    "drifted_resources": [
                        {
                            "resource_type": r["ResourceType"],
                            "logical_id": r["LogicalResourceId"],
                            "drift_status": r["StackResourceDriftStatus"],
                        }
                        for r in drifted.get("StackResourceDrifts", [])
                    ],
                },
            )
        except Exception as e:
            return format_tool_result("detect_drift", {"error": str(e)})


# ── Tool Registry ────────────────────────────────────────────────────


def get_infrastructure_tools() -> list:
    """Return all infrastructure provisioner tools."""
    return [
        terraform_init,
        terraform_plan,
        terraform_apply,
        terraform_destroy,
        terraform_validate,
        terraform_show_state,
        cfn_validate,
        cfn_create_stack,
        cfn_update_stack,
        cfn_delete_stack,
        cfn_describe_stack,
        estimate_cost,
        detect_drift,
    ]
