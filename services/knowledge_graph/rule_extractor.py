import re

ENTITY_PATTERNS = {
    "SYMPTOM": [
        "crashloopbackoff", "oomkilled", "imagepullbackoff", "pending",
        "evicted", "terminating", "unknown", "containercreating",
        "error", "failed", "unhealthy", "not ready", "timeout",
        "high latency", "connection refused", "throttling", "degraded",
        "node pressure", "disk full", "memory leak", "zombie process",
        "stuck terminating", "image pull error", "readiness failure",
        "liveness failure", "restart loop", "high cpu usage",
        "high memory usage", "network partition", "split brain"
    ],
    "ALERT": [
        "kubepodcrashlooping", "kubepodnotready", "nodenotready",
        "kubememoryovercommit", "kubecpuovercommit", "targetdown",
        "watchdog", "alertmanagerdown", "etcdnoleader",
        "kubenodenotready", "kubenodeunreachable", "kubejobfailed",
        "kubedeploymentreplicasmismatch", "kubestatefulsetreplicasmismatch",
        "kubehpareplicasmismatch", "kubepersistentvolumefillingup",
        "kubecontainerwaiting", "kubedaemonsetrolloutstuck",
        "kubequotaalmostfull", "etcdhighnumberoffailedgrpcrequests",
        "etcdmembersdown", "etcdinsufficientmembers",
        "alertmanagerclusterdown", "alertmanagerconfiginconsistent",
        "nodefilesystemspacefillingup", "nodenetworkinterfaceflapping"
    ],
    "ROOT_CAUSE": [
        "out of memory", "resource limit", "missing config",
        "bad image", "network policy", "dns failure", "disk pressure",
        "node failure", "liveness probe", "readiness probe",
        "insufficient resources", "permission denied",
        "wrong image tag", "missing secret", "missing volume",
        "incorrect environment variable", "port conflict",
        "certificate expired", "authentication failure",
        "rbac misconfiguration", "quota exceeded", "node drain",
        "kernel panic", "disk corruption", "network latency",
        "dns resolution failure", "service mesh misconfiguration",
        "wrong labels", "selector mismatch", "taint toleration mismatch",
        "affinity rule conflict", "pod disruption budget violation"
    ],
    "COMPONENT": [
        "pod", "node", "deployment", "service", "ingress", "configmap",
        "secret", "pvc", "persistentvolume", "etcd", "kubelet",
        "scheduler", "controller", "namespace", "replicaset", "daemonset",
        "statefulset", "job", "cronjob", "hpa", "networkpolicy",
        "serviceaccount", "endpoint", "container", "initcontainer",
        "sidecar", "volume", "storageclass", "resourcequota",
        "limitrange", "poddisruptionbudget", "clusterrole", "rolebinding",
        "apiserver", "controllermanager", "coredns", "kubeproxy",
        "containerd", "docker", "csi driver", "cni plugin"
    ],
    "RESOLUTION": [
        "restart pod", "increase memory limit", "check logs",
        "describe pod", "scale deployment", "rollback", "kubectl logs",
        "kubectl describe", "resource quota", "horizontal pod autoscaler",
        "delete pod", "drain node", "cordon node", "uncordon node",
        "update image", "fix dns", "renew certificate",
        "adjust resource requests", "fix rbac", "patch deployment",
        "restart kubelet", "restart etcd", "increase disk space",
        "clear evicted pods", "fix liveness probe", "fix readiness probe",
        "update network policy", "scale node pool", "taint node",
        "add toleration", "fix affinity rules"
    ]
}

RELATIONSHIP_RULES = [
    ("oomkilled", "out of memory", "CAUSES"),
    ("crashloopbackoff", "liveness probe", "CAUSES"),
    ("crashloopbackoff", "bad image", "CAUSES"),
    ("crashloopbackoff", "check logs", "RESOLVES"),
    ("crashloopbackoff", "kubectl logs", "RESOLVES"),
    ("crashloopbackoff", "restart pod", "RESOLVES"),
    ("oomkilled", "increase memory limit", "RESOLVES"),
    ("oomkilled", "pod", "AFFECTS"),
    ("nodenotready", "node failure", "CAUSES"),
    ("nodenotready", "disk pressure", "CAUSES"),
    ("nodenotready", "kubelet", "AFFECTS"),
    ("nodenotready", "drain node", "RESOLVES"),
    ("imagepullbackoff", "bad image", "CAUSES"),
    ("imagepullbackoff", "wrong image tag", "CAUSES"),
    ("imagepullbackoff", "update image", "RESOLVES"),
    ("pending", "insufficient resources", "CAUSES"),
    ("pending", "resource quota", "RESOLVES"),
    ("pending", "taint toleration mismatch", "CAUSES"),
    ("pending", "add toleration", "RESOLVES"),
    ("evicted", "disk pressure", "CAUSES"),
    ("evicted", "out of memory", "CAUSES"),
    ("evicted", "clear evicted pods", "RESOLVES"),
    ("error", "check logs", "RESOLVES"),
    ("failed", "kubectl describe", "RESOLVES"),
    ("unhealthy", "liveness probe", "CAUSES"),
    ("unhealthy", "readiness probe", "CAUSES"),
    ("unhealthy", "fix liveness probe", "RESOLVES"),
    ("timeout", "network policy", "CAUSES"),
    ("timeout", "network latency", "CAUSES"),
    ("kubememoryovercommit", "out of memory", "CAUSES"),
    ("kubecpuovercommit", "resource limit", "CAUSES"),
    ("kubepodcrashlooping", "crashloopbackoff", "INDICATES"),
    ("kubepodnotready", "pending", "INDICATES"),
    ("nodenotready", "kubenodenotready", "INDICATES"),
    ("etcdmembersdown", "etcd", "AFFECTS"),
    ("etcdnoleader", "etcd", "AFFECTS"),
    ("dns failure", "coredns", "AFFECTS"),
    ("dns failure", "fix dns", "RESOLVES"),
    ("permission denied", "rbac misconfiguration", "CAUSES"),
    ("permission denied", "fix rbac", "RESOLVES"),
    ("certificate expired", "renew certificate", "RESOLVES"),
    ("quota exceeded", "resourcequota", "AFFECTS"),
    ("selector mismatch", "service", "AFFECTS"),
    ("network partition", "network policy", "CAUSES"),
    ("disk full", "increase disk space", "RESOLVES"),
    ("high cpu usage", "kubecpuovercommit", "INDICATES"),
    ("high memory usage", "kubememoryovercommit", "INDICATES"),
]

def extract_entities_rule_based(chunk: dict) -> dict:
    """Extract entities using keyword matching — no LLM required."""
    text_lower = chunk["text"].lower()
    entities = []
    found_names = set()

    for entity_type, keywords in ENTITY_PATTERNS.items():
        for keyword in keywords:
            if keyword in text_lower and keyword not in found_names:
                entities.append({
                    "name": keyword,
                    "type": entity_type,
                    "description": f"Found in {chunk['metadata'].get('title', 'document')}"
                })
                found_names.add(keyword)

    relationships = []
    for source, target, rel_type in RELATIONSHIP_RULES:
        if source in found_names and target in found_names:
            relationships.append({
                "source": source,
                "target": target,
                "type": rel_type
            })

    return {
        "entities": entities,
        "relationships": relationships,
        "source_url": chunk["metadata"].get("source_url", ""),
        "title": chunk["metadata"].get("title", ""),
        "source": chunk["metadata"].get("source", "")
    }