import os
import subprocess
import openpyxl

# Define EKS cluster details for idev
EKS_CLUSTER = {
    "cluster_name": "idev-cluster-name",
    "region": "us-west-2",
    "aws_access_key": "YOUR_IDEV_AWS_ACCESS_KEY",
    "aws_secret_key": "YOUR_IDEV_AWS_SECRET_KEY"
}

EXCEL_FILE = "eks_pod_os_versions.xlsx"

def set_aws_credentials(access_key, secret_key):
    """Set AWS credentials dynamically."""
    os.environ["AWS_ACCESS_KEY_ID"] = access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
    print("AWS credentials set successfully.")

def switch_eks_cluster(cluster_name, region):
    """Switch context to the given EKS cluster."""
    command = [
        "aws", "eks", "update-kubeconfig",
        "--region", region,
        "--name", cluster_name
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print(f"Switched to {cluster_name}")
            return True
        else:
            print(f"Failed to switch to {cluster_name}: {result.stderr.decode('utf-8').strip()}")
            return False
    except Exception as e:
        print(f"Error switching cluster: {e}")
        return False

def get_application_namespaces():
    """Fetch all namespaces, excluding system namespaces, using kubectl."""
    try:
        result = subprocess.run(["kubectl", "get", "ns", "-o", "jsonpath={.items[*].metadata.name}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        namespaces = result.stdout.decode('utf-8').strip().split()
        excluded_ns = {"kube-system", "kube-public", "kube-node-lease"}
        return [ns for ns in namespaces if ns not in excluded_ns]
    except Exception as e:
        print(f"Error getting namespaces: {e}")
        return []

def get_pods_in_namespace(namespace):
    """Fetch all pods running in a given namespace using kubectl."""
    try:
        result = subprocess.run(["kubectl", "get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode('utf-8').strip().split()
    except Exception as e:
        print(f"Error getting pods in {namespace}: {e}")
        return []

def get_pod_os_version(namespace, pod):
    """Execute 'uname -r' inside a pod and return the OS version using kubectl."""
    command = ["kubectl", "exec", "-n", namespace, pod, "--", "uname", "-r"]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode('utf-8').strip()
    except Exception as e:
        return f"Error: {e}"

def collect_cluster_data():
    """Collect OS version data for all pods in the idev cluster."""
    data = []

    for namespace in get_application_namespaces():
        for pod in get_pods_in_namespace(namespace):
            os_version = get_pod_os_version(namespace, pod)
            data.append([namespace, pod, os_version])

    return data

def save_to_excel(data):
    """Save collected data into an Excel file."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "idev"

    # Write header
    sheet.append(["Namespace", "Pod Name", "OS Version"])

    # Write data rows
    for row in data:
        sheet.append(row)

    workbook.save(EXCEL_FILE)
    print(f"OS version details saved to {EXCEL_FILE}")

def main():
    set_aws_credentials(EKS_CLUSTER["aws_access_key"], EKS_CLUSTER["aws_secret_key"])

    if switch_eks_cluster(EKS_CLUSTER["cluster_name"], EKS_CLUSTER["region"]):
        data = collect_cluster_data()
        if data:
            save_to_excel(data)
        else:
            print("No data collected.")

if __name__ == "__main__":
    main()


