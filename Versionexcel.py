import os
import subprocess
import pandas as pd

# Define idev cluster details
EKS_CLUSTER = {
    "cluster_name": "idev-cluster-name",
    "region": "us-west-2",
    "aws_access_key": "YOUR_IDEV_AWS_ACCESS_KEY",
    "aws_secret_key": "YOUR_IDEV_AWS_SECRET_KEY"
}

EXCEL_FILE = "eks_pod_os_versions_idev.xlsx"

def set_aws_credentials(aws_access_key, aws_secret_key):
    """Set AWS credentials dynamically."""
    os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    print("AWS credentials set successfully.")

def switch_eks_cluster(cluster_name, region):
    """Switch context to the given EKS cluster."""
    command = [
        "aws", "eks", "update-kubeconfig",
        "--region", region,
        "--name", cluster_name
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
        print(f"Switched to {cluster_name}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to switch to {cluster_name}: {e.stderr.strip()}")
        return False
    return True

def get_application_namespaces():
    """Fetch all namespaces, excluding system namespaces, using kubectl."""
    try:
        result = subprocess.run(["kubectl", "get", "ns", "-o", "jsonpath={.items[*].metadata.name}"],
                                capture_output=True, text=True, check=True)
        namespaces = result.stdout.split()
        excluded_ns = {"kube-system", "kube-public", "kube-node-lease"}
        return [ns for ns in namespaces if ns not in excluded_ns]
    except subprocess.CalledProcessError as e:
        print(f"Error getting namespaces: {e.stderr.strip()}")
        return []

def get_pods_in_namespace(namespace):
    """Fetch all pods running in a given namespace using kubectl."""
    try:
        result = subprocess.run(["kubectl", "get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"],
                                capture_output=True, text=True, check=True)
        return result.stdout.split()
    except subprocess.CalledProcessError as e:
        print(f"Error getting pods in {namespace}: {e.stderr.strip()}")
        return []

def get_pod_os_version(namespace, pod):
    """Execute 'uname -r' inside a pod and return the OS version using kubectl."""
    command = ["kubectl", "exec", "-n", namespace, pod, "--", "uname", "-r"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"

def collect_cluster_data():
    """Collect OS version data for all pods in the idev EKS cluster."""
    data = []
    
    for namespace in get_application_namespaces():
        for pod in get_pods_in_namespace(namespace):
            os_version = get_pod_os_version(namespace, pod)
            data.append([namespace, pod, os_version])

    return pd.DataFrame(data, columns=["Namespace", "Pod Name", "OS Version"])

def main():
    set_aws_credentials(EKS_CLUSTER["aws_access_key"], EKS_CLUSTER["aws_secret_key"])

    if switch_eks_cluster(EKS_CLUSTER["cluster_name"], EKS_CLUSTER["region"]):
        df = collect_cluster_data()

        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="idev", index=False)

        print(f"OS version details saved to {EXCEL_FILE}")

if __name__ == "__main__":
    main()

