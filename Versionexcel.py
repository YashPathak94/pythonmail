

import os
import subprocess
import pandas as pd

# Define idev cluster details
IDEV_CLUSTER = {
    "cluster_name": "your-idev-cluster",  # Replace with actual cluster name
    "region": "us-west-2"  # Replace with actual region
}

EXCEL_FILE = "idev_pod_image_tags.xlsx"

def switch_eks_cluster(cluster_name, region):
    """Switch to the idev EKS cluster using AWS CLI."""
    command = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
    subprocess.run(command, shell=True, check=True)
    print(f"Switched to cluster: {cluster_name}")

def get_all_namespaces():
    """Fetch all namespaces excluding system namespaces."""
    try:
        cmd = "kubectl get ns -o jsonpath='{.items[*].metadata.name}'"
        result = subprocess.check_output(cmd, shell=True, text=True).strip()
        
        namespaces = result.split()
        excluded_ns = {"kube-system", "kube-public", "kube-node-lease"}
        return [ns for ns in namespaces if ns not in excluded_ns]
    except subprocess.CalledProcessError as e:
        print("Error getting namespaces:", e)
        return []

def get_pod_image_tags(namespace):
    """Fetch pod names and their container image tags in a given namespace."""
    try:
        cmd_pods = f"kubectl get pods -n {namespace} -o jsonpath='{{.items[*].metadata.name}}'"
        cmd_images = f"kubectl get pods -n {namespace} -o jsonpath='{{.items[*].spec.containers[*].image}}'"

        pods = subprocess.check_output(cmd_pods, shell=True, text=True).strip().split()
        images = subprocess.check_output(cmd_images, shell=True, text=True).strip().split()

        # Extract only the tag part (after last ":")
        image_tags = [img.split(":")[-1] if ":" in img else "latest" for img in images]

        return list(zip([namespace] * len(pods), pods, image_tags))
    except subprocess.CalledProcessError:
        print(f"Error fetching pods/images in namespace: {namespace}")
        return []

def main():
    """Main function to collect pod image tags for all namespaces in idev cluster."""
    switch_eks_cluster(IDEV_CLUSTER["cluster_name"], IDEV_CLUSTER["region"])
    
    all_data = []

    for namespace in get_all_namespaces():
        all_data.extend(get_pod_image_tags(namespace))

    # Convert data to DataFrame
    df = pd.DataFrame(all_data, columns=["Namespace", "Pod Name", "Tag Version"])

    # Save to Excel (single sheet)
    df.to_excel(EXCEL_FILE, sheet_name="idev_cluster_pods", index=False)

    print(f"Saved pod image tags to {EXCEL_FILE}")

if __name__ == "__main__":
    main()

