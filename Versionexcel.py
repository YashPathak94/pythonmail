

import os
import subprocess
import openpyxl

# Define EKS cluster details for idev
EKS_CLUSTER = {
    "cluster_name": "dev",
    "region": "us-west-2",
    "aws_access_key": "YOUR_ACCESS_KEY",
    "aws_secret_key": "YOUR_SECRET_KEY",
    "aws_session_token": "YOUR_SESSION_TOKEN"
}

EXCEL_FILE = "eks_pod_os_versions.xlsx"

def set_aws_credentials(aws_access_key, aws_secret_key, aws_session_token):
    """Set AWS credentials dynamically."""
    os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    os.environ["AWS_SESSION_TOKEN"] = aws_session_token
    print("AWS credentials set successfully.")

def switch_eks_cluster(cluster_name, region):
    """Switch context to the given EKS cluster."""
    command = ["aws", "eks", "update-kubeconfig", "--region", region, "--name", cluster_name]
    
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return True
        else:
            print(f"Failed to switch to {cluster_name}: {result.stderr.decode('utf-8')}")
            return False
    except Exception as e:
        print(f"Error switching cluster: {e}")
        return False

def get_application_namespaces():
    """Fetch all namespaces excluding system namespaces, using kubectl."""
    try:
        command = ["/usr/local/bin/kubectl", "get", "ns", "-o", "jsonpath={.items[*].metadata.name}"]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        namespaces = result.stdout.decode("utf-8").strip().split()

        # Exclude system namespaces
        excluded_ns = ["kube-system", "kube-public", "kube-node-lease"]
        return [ns for ns in namespaces if ns not in excluded_ns]
    
    except Exception as e:
        print(f"Error getting namespaces: {e}")
        return []

def get_pods_in_namespace(namespace):
    """Fetch all pods running in a given namespace using kubectl."""
    try:
        command = ["/usr/local/bin/kubectl", "get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode("utf-8").strip().split()
    except Exception as e:
        print(f"Error getting pods in namespace [{namespace}]: {e}")
        return []

def get_pod_os_version(namespace, pod):
    """Execute 'uname -r' inside a pod and return the OS version using kubectl."""
    try:
        command = ["/usr/local/bin/kubectl", "exec", "-n", namespace, pod, "--", "uname", "-r"]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode("utf-8").strip()
    except Exception as e:
        print(f"Error getting OS version for pod [{pod}] in namespace [{namespace}]: {e}")
        return "N/A"

def get_pod_image_tag(namespace, pod):
    """Fetch the image tag of a pod's container using kubectl."""
    try:
        command = [
            "/usr/local/bin/kubectl", "get", "pod", pod, "-n", namespace,
            "-o", "jsonpath={.spec.containers[*].image}"
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        images = result.stdout.decode("utf-8").strip().split()

        # Extract tags from the full image path
        tags = [img.split(":")[-1] if ":" in img else "latest" for img in images]
        return ", ".join(tags)  # Combine multiple tags if multiple containers exist
    except Exception as e:
        print(f"Error getting image tag for pod [{pod}] in namespace [{namespace}]: {e}")
        return "N/A"

def collect_cluster_data():
    """Collect OS version and image tag for all pods in the idev cluster."""
    data = []

    for namespace in get_application_namespaces():
        for pod in get_pods_in_namespace(namespace):
            os_version = get_pod_os_version(namespace, pod)
            image_tag = get_pod_image_tag(namespace, pod)
            data.append([namespace, pod, os_version, image_tag])

    return data

def save_to_excel(data):
    """Save collected data into an Excel file."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "idev"

    # Write header
    sheet.append(["Namespace", "Pod Name", "OS Version", "Image Tag"])

    # Write data rows
    for row in data:
        sheet.append(row)

    workbook.save(EXCEL_FILE)
    print(f"Data saved to {EXCEL_FILE}")

def main():
    set_aws_credentials(EKS_CLUSTER["aws_access_key"], EKS_CLUSTER["aws_secret_key"], EKS_CLUSTER["aws_session_token"])
    
    if switch_eks_cluster(EKS_CLUSTER["cluster_name"], EKS_CLUSTER["region"]):
        data = collect_cluster_data()
        if data:
            save_to_excel(data)
        else:
            print("No data collected.")

if __name__ == "__main__":
    main()
