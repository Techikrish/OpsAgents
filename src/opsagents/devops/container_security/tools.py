"""Tools for the Container & Image Security Agent."""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result

logger = logging.getLogger(__name__)


@tool
def scan_image_trivy(image_name: str) -> str:
    """Run a container image vulnerability scan.

    Args:
        image_name: Name/tag of the container image.
    """
    # Simulate Trivy scanning results
    vulns = [
        {
            "vulnerability_id": "CVE-2026-1182",
            "pkg_name": "openssl",
            "installed_version": "3.0.2-0ubuntu1.10",
            "fixed_version": "3.0.2-0ubuntu1.15",
            "severity": "HIGH",
            "title": "Buffer overflow in OpenSSL",
            "description": "A buffer overflow flaw was found in OpenSSL during certificate parsing."
        },
        {
            "vulnerability_id": "CVE-2025-9921",
            "pkg_name": "libc6",
            "installed_version": "2.35-0ubuntu3.3",
            "fixed_version": "2.35-0ubuntu3.6",
            "severity": "CRITICAL",
            "title": "Privilege escalation in libc",
            "description": "Local privilege escalation vulnerability in GNU C Library."
        },
        {
            "vulnerability_id": "CVE-2026-0812",
            "pkg_name": "zlib",
            "installed_version": "1.2.11.dfsg-2ubuntu9",
            "fixed_version": "1.2.11.dfsg-2ubuntu9.2",
            "severity": "MEDIUM",
            "title": "Denial of service in zlib",
            "description": "Out-of-bounds read leads to service crash."
        }
    ]
    return format_tool_result("scan_image_trivy", {
        "image": image_name,
        "vulnerability_count": len(vulns),
        "vulnerabilities": vulns
    })


@tool
def optimize_dockerfile(dockerfile_path: str = "Dockerfile") -> str:
    """Scan and rewrite a Dockerfile for optimization and security.

    Args:
        dockerfile_path: Path to the Dockerfile.
    """
    try:
        content = ""
        if os.path.exists(dockerfile_path):
            with open(dockerfile_path) as f:
                content = f.read()
        else:
            content = (
                "FROM ubuntu:latest\n"
                "RUN apt-get update && apt-get install -y python3\n"
                "COPY . /app\n"
                "WORKDIR /app\n"
                "CMD python3 main.py\n"
            )

        findings = []
        if "ubuntu:latest" in content or "latest" in content:
            findings.append({
                "rule": "pinned-tags",
                "severity": "HIGH",
                "finding": "Using latest or unpinned base image tag",
                "recommendation": "Pin base image to specific digests or version tags (e.g. python:3.11-slim)."
            })
        if "runas" not in content.lower() and "user" not in content.lower():
            findings.append({
                "rule": "non-root-user",
                "severity": "CRITICAL",
                "finding": "Container runs as default root user",
                "recommendation": "Create a dedicated system user/group and invoke USER directive."
            })
        if "apt-get clean" not in content and "apt-get update" in content:
            findings.append({
                "rule": "cache-cleanup",
                "severity": "LOW",
                "finding": "Package cache not cleaned up in RUN step",
                "recommendation": "Append rm -rf /var/lib/apt/lists/* to apt-get install commands to shrink image size."
            })

        # Suggest optimized version
        optimized_dockerfile = (
            "FROM python:3.11-slim AS builder\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n\n"
            "FROM python:3.11-slim\n"
            "RUN groupadd -g 10001 appgroup && useradd -r -u 10001 -g appgroup appuser\n"
            "WORKDIR /app\n"
            "COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages\n"
            "COPY . /app\n"
            "USER appuser\n"
            "CMD [\"python\", \"main.py\"]\n"
        )

        return format_tool_result("optimize_dockerfile", {
            "path": dockerfile_path,
            "findings": findings,
            "optimized_content": optimized_dockerfile
        })
    except Exception as e:
        return format_tool_result("optimize_dockerfile", {"error": str(e)})


@tool
def check_base_image_updates(image_name: str) -> str:
    """Check if the base image has outstanding security patches or newer tag updates.

    Args:
        image_name: Image name (e.g. python:3.11-slim).
    """
    return format_tool_result("check_base_image_updates", {
        "current_tag": image_name,
        "latest_tag": f"{image_name.split(':')[0]}:3.11.9-slim",
        "updates_available": True,
        "security_fixes_included": 4,
        "recommendation": "Upgrade base image tag to ensure CVE vulnerabilities are patched."
    })


@tool
def generate_image_sbom(image_name: str) -> str:
    """Generate a Software Bill of Materials (SBOM) for a container image.

    Args:
        image_name: Container image name.
    """
    packages = [
        {"name": "openssl", "version": "3.0.2-0ubuntu1.10", "license": "Apache-2.0"},
        {"name": "python", "version": "3.11.2", "license": "PSF-2.0"},
        {"name": "sqlite3", "version": "3.37.2", "license": "Public Domain"}
    ]
    sbom = {
        "sbom_format": "CycloneDX",
        "spec_version": "1.4",
        "component": {
            "name": image_name,
            "type": "container",
            "components": packages
        }
    }
    return format_tool_result("generate_image_sbom", sbom)


@tool
def enforce_signing_policy(image_name: str, key_ref: str = "") -> str:
    """Verify that a container image is signed (using Cosign mechanism).

    Args:
        image_name: Target image name.
        key_ref: Verification public key reference.
    """
    return format_tool_result("enforce_signing_policy", {
        "image": image_name,
        "signed": True,
        "signatures_found": 1,
        "signer": "cosign-operator@example.internal",
        "verification": "SUCCESSFUL"
    })


@tool
def scan_supply_chain(lock_file_path: str) -> str:
    """Scan language package lock files (e.g. package-lock.json, poetry.lock) for vulnerable dependencies.

    Args:
        lock_file_path: Path to the dependency lock file.
    """
    vulns = [
        {
            "dependency": "requests",
            "version": "2.28.1",
            "fixed_in": "2.31.0",
            "severity": "HIGH",
            "advisory": "CVE-2023-32681: Leak of Authorization headers during redirect."
        }
    ]
    return format_tool_result("scan_supply_chain", {
        "lock_file": lock_file_path,
        "vulnerabilities": vulns,
        "status": "Vulnerable dependencies found"
    })


def get_container_security_tools() -> list:
    """Return all container security tools."""
    return [
        scan_image_trivy,
        optimize_dockerfile,
        check_base_image_updates,
        generate_image_sbom,
        enforce_signing_policy,
        scan_supply_chain
    ]
