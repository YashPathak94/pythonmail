from kubernetes import client, config
import subprocess
import pandas as pd

def get_application_namespaces():
    """Fetch all namespaces, excluding system namespaces."""
    v1 = client.CoreV1Api()
    excluded_ns = {"kube-system", "kube-public", "kube-node-lease"}
    return [ns.metadata.name for ns in v1.list_namespace().items if ns.metadata.name not in excluded_ns]

def get_pods_in_namespace(namespace):
    """Fetch all pods running in a given namespace."""
    v1 = client.CoreV1Api()
    return [pod.metadata.name for pod in v1.list_namespaced_pod(namespace).items]

def get_pod_os_version(namespace, pod):
    """Execute 'uname -r' inside a pod and return the OS version."""
    command = ["kubectl", "exec", "-n", namespace, pod, "--", "uname", "-r"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"

def main():
    # Load Kubernetes config
    config.load_kube_config()
    
    data = []
    
    for namespace in get_application_namespaces():
        for pod in get_pods_in_namespace(namespace):
            os_version = get_pod_os_version(namespace, pod)
            data.append([namespace, pod, os_version])
    
    # Convert to DataFrame
    df = pd.DataFrame(data, columns=["Namespace", "Pod Name", "OS Version"])
    
    # Save to Excel
    excel_file = "pod_os_versions.xlsx"
    df.to_excel(excel_file, index=False, engine='openpyxl')
    
    print(f"OS version details saved to {excel_file}")

if __name__ == "__main__":
    main()
