

import boto3
import subprocess
import pandas as pd

# Function to retrieve AWS credentials dynamically
def get_aws_credentials():
    session = boto3.Session()  # Create a session
    credentials = session.get_credentials()  # Get credentials
    creds = credentials.get_frozen_credentials()  # Convert to a frozen form

    return {
        "aws_access_key_id": creds.access_key,
        "aws_secret_access_key": creds.secret_key,
        "aws_session_token": creds.token
    }

# Function to switch AWS credentials dynamically
def set_aws_credentials():
    creds = get_aws_credentials()
    subprocess.run([
        "export",
        f"AWS_ACCESS_KEY_ID={creds['aws_access_key_id']}",
        f"AWS_SECRET_ACCESS_KEY={creds['aws_secret_access_key']}",
        f"AWS_SESSION_TOKEN={creds['aws_session_token']}"
    ], shell=True, check=True)
    print("AWS credentials set successfully.")

# Function to get all namespaces from the cluster
def get_all_namespaces():
    try:
        result = subprocess.run(["kubectl", "get", "namespaces", "-o", "jsonpath={.items[*].metadata.name}"], 
                                capture_output=True, text=True, check=True)
        namespaces = result.stdout.strip().split()
        return namespaces
    except Exception as e:
        print(f"Error getting namespaces: {e}")
        return []

# Function to get image tags from all pods in a given namespace
def get_pod_image_tags(namespace):
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].spec.containers[*].image}"],
            capture_output=True, text=True, check=True
        )
        images = result.stdout.strip().split()
        image_tags = [img.split(":")[-1] if ":" in img else "latest" for img in images]
        return image_tags
    except Exception as e:
        print(f"Error fetching image tags in namespace {namespace}: {e}")
        return []

# Main function
def main():
    set_aws_credentials()  # Set AWS credentials

    cluster_name = "idev-cluster"  # Change to your cluster name
    namespaces = get_all_namespaces()

    data = []
    for namespace in namespaces:
        image_tags = get_pod_image_tags(namespace)
        for tag in image_tags:
            data.append({"Namespace": namespace, "Tag Version": tag})

    # Convert to DataFrame and save to Excel
    df = pd.DataFrame(data)
    df.to_excel("pod_image_tags.xlsx", index=False)
    print("Excel file generated: pod_image_tags.xlsx")

if __name__ == "__main__":
    main()
