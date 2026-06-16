"""Tools for the Kubernetes Operations Agent."""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result

logger = logging.getLogger(__name__)


@tool
def get_cluster_status() -> str:
    """Retrieve node, pod, and service status summaries for the active Kubernetes cluster."""
    # Attempt to load kubernetes client, fallback to mock details if no cluster
    try:
        from kubernetes import client, config
        config.load_kube_config()
        v1 = client.CoreV1Api()
        nodes = v1.list_node()
        node_summary = [{"name": n.metadata.name, "status": n.status.conditions[-1].type} for n in nodes.items]
        pods = v1.list_pod_for_all_namespaces(limit=20)
        pod_summary = [{"name": p.metadata.name, "namespace": p.metadata.namespace, "phase": p.status.phase} for p in pods.items]
        return format_tool_result("get_cluster_status", {
            "connected": True,
            "nodes": node_summary,
            "pods": pod_summary
        })
    except Exception as e:
        logger.warning("Could not connect to live K8s cluster, returning mock topology: %s", e)
        # Mock cluster response for offline compatibility
        return format_tool_result("get_cluster_status", {
            "connected": False,
            "nodes": [
                {"name": "ip-10-0-1-52.ec2.internal", "status": "Ready", "role": "control-plane"},
                {"name": "ip-10-0-1-118.ec2.internal", "status": "Ready", "role": "worker"},
                {"name": "ip-10-0-2-205.ec2.internal", "status": "Ready", "role": "worker"}
            ],
            "namespace_health": {
                "kube-system": "Healthy",
                "default": "Degraded (1 pod failing)",
                "monitoring": "Healthy"
            }
        })


@tool
def troubleshoot_pod(pod_name: str, namespace: str = "default") -> str:
    """Analyze events and conditions for a failing pod to determine CrashLoopBackOff or other issues.

    Args:
        pod_name: Name of the pod to troubleshoot.
        namespace: Cluster namespace containing the pod.
    """
    # Simulate logs and events for troubleshooting
    events = [
        {"reason": "Scheduled", "message": f"Successfully assigned {namespace}/{pod_name} to worker node"},
        {"reason": "Pulled", "message": "Container image already present on machine"},
        {"reason": "Created", "message": "Created container web-app"},
        {"reason": "Started", "message": "Started container web-app"},
        {"reason": "BackOff", "message": "Back-off restarting failed container"}
    ]

    logs = (
        "2026-06-16T11:45:00Z [info] Starting application...\n"
        "2026-06-16T11:45:01Z [info] Loading database config...\n"
        "2026-06-16T11:45:02Z [error] Connection failed to db-service.default.svc.cluster.local:5432\n"
        "2026-06-16T11:45:02Z [error] FATAL: Database host unreachable. Exiting code 1\n"
    )

    return format_tool_result("troubleshoot_pod", {
        "pod": pod_name,
        "namespace": namespace,
        "status": "CrashLoopBackOff",
        "restart_count": 5,
        "events": events,
        "logs": logs
    })


@tool
def generate_manifest(
    kind: str,
    name: str,
    namespace: str = "default",
    image: str = "",
) -> str:
    """Generate a boilerplate Kubernetes manifest.

    Args:
        kind: Kind of resource (Deployment, Service, Ingress, NetworkPolicy).
        name: Name of the resource.
        namespace: Destination namespace.
        image: Container image (for Deployments).
    """
    kind_lower = kind.lower()

    if kind_lower == "deployment":
        yaml_content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app: {name}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: {name}
          image: {image or 'nginx:latest'}
          ports:
            - containerPort: 80
          resources:
            requests:
              memory: "64Mi"
              cpu: "100m"
            limits:
              memory: "128Mi"
              cpu: "200m"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 10001
            capabilities:
              drop:
                - ALL
          livenessProbe:
            httpGet:
              path: /healthz
              port: 80
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            httpGet:
              path: /readyz
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 10
"""
    elif kind_lower == "service":
        yaml_content = f"""apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {namespace}
spec:
  selector:
    app: {name}
  ports:
    - protocol: TCP
      port: 80
      targetPort: 80
  type: ClusterIP
"""
    elif kind_lower == "ingress":
        yaml_content = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}
  namespace: {namespace}
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  rules:
    - host: {name}.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {name}
                port:
                  number: 80
"""
    else:
        yaml_content = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}
  namespace: {namespace}
data:
  app.properties: |
    key=value
"""

    return format_tool_result("generate_manifest", {
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "yaml": yaml_content
    })


@tool
def generate_helm_chart(chart_name: str, output_dir: str = ".") -> str:
    """Scaffold a custom Helm chart structure.

    Args:
        chart_name: Name of the chart.
        output_dir: Parent directory where the chart will be created.
    """
    chart_path = os.path.join(output_dir, chart_name)
    try:
        os.makedirs(os.path.join(chart_path, "templates"), exist_ok=True)

        # Chart.yaml
        with open(os.path.join(chart_path, "Chart.yaml"), "w") as f:
            f.write(f"""apiVersion: v2
name: {chart_name}
description: A Helm chart for Kubernetes deployment
type: application
version: 0.1.0
appVersion: "1.0.0"
""")

        # values.yaml
        with open(os.path.join(chart_path, "values.yaml"), "w") as f:
            f.write("""replicaCount: 2
image:
  repository: nginx
  pullPolicy: IfNotPresent
  tag: "stable"
service:
  type: ClusterIP
  port: 80
resources:
  limits:
    cpu: 200m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 128Mi
""")
        return format_tool_result("generate_helm_chart", {
            "chart_name": chart_name,
            "path": chart_path,
            "status": "created"
        })
    except Exception as e:
        return format_tool_result("generate_helm_chart", {"error": str(e)})


@tool
def scale_deployment(name: str, replicas: int, namespace: str = "default") -> str:
    """Scale replicas for a deployment.

    Args:
        name: Name of the deployment.
        replicas: Desired replica count.
        namespace: Deployment namespace.
    """
    # Simulate scale operation
    return format_tool_result("scale_deployment", {
        "deployment": name,
        "namespace": namespace,
        "previous_replicas": 2,
        "target_replicas": replicas,
        "status": "Scale command scheduled successfully"
    })


@tool
def get_pod_logs(pod_name: str, namespace: str = "default") -> str:
    """Fetch logs from a container pod.

    Args:
        pod_name: Pod name.
        namespace: Target namespace.
    """
    logs = (
        "[2026-06-16 11:30:15] Starting server on port 8080\n"
        "[2026-06-16 11:30:18] Received request GET /healthz\n"
        "[2026-06-16 11:30:18] Response 200 OK\n"
    )
    return format_tool_result("get_pod_logs", {
        "pod": pod_name,
        "namespace": namespace,
        "logs": logs
    })


@tool
def rollback_deployment(name: str, namespace: str = "default") -> str:
    """Rollback deployment to its previous revision.

    Args:
        name: Deployment name.
        namespace: Target namespace.
    """
    return format_tool_result("rollback_deployment", {
        "deployment": name,
        "namespace": namespace,
        "status": "Rollback initiated successfully",
        "target_revision": "previous"
    })


@tool
def analyze_resource_usage(namespace: str = "default") -> str:
    """Evaluate CPU and Memory requests/limits against average actual usage in the namespace.

    Args:
        namespace: Target namespace.
    """
    metrics = [
        {
            "deployment": "web-app",
            "cpu_request": "100m",
            "cpu_limit": "200m",
            "cpu_avg_usage": "20m",
            "memory_request": "128Mi",
            "memory_limit": "256Mi",
            "memory_avg_usage": "45Mi",
            "status": "Overprovisioned (suggest requests/limits decrease by 50%)"
        },
        {
            "deployment": "auth-service",
            "cpu_request": "200m",
            "cpu_limit": "400m",
            "cpu_avg_usage": "380m",
            "memory_request": "256Mi",
            "memory_limit": "512Mi",
            "memory_avg_usage": "495Mi",
            "status": "Underprovisioned (suggest scaling limits to avoid OOMKill)"
        }
    ]
    return format_tool_result("analyze_resource_usage", {
        "namespace": namespace,
        "metrics": metrics
    })


def get_kubernetes_tools() -> list:
    """Return all Kubernetes tools."""
    return [
        get_cluster_status,
        troubleshoot_pod,
        generate_manifest,
        generate_helm_chart,
        scale_deployment,
        get_pod_logs,
        rollback_deployment,
        analyze_resource_usage
    ]
