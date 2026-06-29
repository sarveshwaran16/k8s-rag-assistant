K8S_KEYWORDS = [
    # Core objects
    "pod", "pods", "node", "nodes", "cluster", "kubernetes", "k8s",
    "deployment", "deployments", "service", "services", "container",
    "containers", "namespace", "namespaces", "replicaset", "daemonset",
    "statefulset", "job", "jobs", "cronjob", "hpa", "endpoint", "endpoints",
    "ingress", "configmap", "configmaps", "secret", "secrets", "pvc",
    "pv", "persistentvolume", "volume", "volumes", "etcd", "kubelet",
    "scheduler", "controller", "label", "labels", "selector", "selectors",
    "taint", "taints", "toleration", "tolerations", "affinity",
    "loadbalancer", "load balancer", "nodeport", "clusterip",

    # Common failure states / symptoms
    "crashloopbackoff", "crash loop", "crashloop", "oomkilled", "oom",
    "imagepullbackoff", "image pull", "imagepull", "pull failure",
    "pull error", "pending", "evicted", "eviction", "terminating",
    "containercreating", "container creating", "errimageneverpull",
    "errimagepull", "nodenotready", "node not ready", "unhealthy",
    "unreachable", "not ready",

    # Generic operational vocabulary commonly used in K8s troubleshooting
    "restart", "restarting", "restarts", "crash", "crashing", "crashes",
    "error", "errors", "failed", "failing", "failure", "failures",
    "timeout", "timing out", "throttle", "throttling", "throttled",
    "rollout", "rollback", "rolling update", "scale", "scaling",
    "autoscale", "autoscaling", "5xx", "503", "502", "500", "latency",
    "registry", "manifest", "tag", "image", "images",

    # Infra / platform terms
    "dns", "network", "networking", "rbac", "role", "rolebinding",
    "clusterrole", "quota", "resourcequota", "limitrange", "resource",
    "resources", "limit", "limits", "request", "requests", "cpu",
    "memory", "disk", "storage", "storageclass", "probe", "probes",
    "liveness", "readiness", "startup probe", "helm", "docker",
    "minikube", "kind", "eks", "gke", "aks", "api server", "apiserver",
    "coredns", "kube-dns", "csi", "cni", "ingress controller",

    # Commands / tools
    "kubectl", "kubeconfig", "yaml", "manifest file", "podspec",
    "deployment spec",

    # Common phrasing patterns for troubleshooting questions
    "debug", "debugging", "diagnose", "diagnosing", "troubleshoot",
    "troubleshooting", "investigate", "investigating", "stuck",
    "won't start", "wont start", "not starting", "keeps restarting",
    "keeps crashing", "keeps failing",
]


def is_in_scope(query: str) -> bool:
    """Check if the query is plausibly about Kubernetes/SRE topics."""
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in K8S_KEYWORDS)


def check_scope_node(state: dict) -> dict:
    """LangGraph node — gate query before running expensive retrieval/generation."""
    in_scope = is_in_scope(state["query"])
    if not in_scope:
        return {
            "in_scope": False,
            "answer": (
                "This assistant is scoped to Kubernetes and SRE troubleshooting questions. "
                "Your question doesn't appear to be about Kubernetes — please rephrase it "
                "around a specific Kubernetes symptom, component, or error (e.g. "
                "'Why is my pod in CrashLoopBackOff?')."
            ),
            "sources": []
        }
    return {"in_scope": True}