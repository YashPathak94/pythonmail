
import os
import subprocess
import json
import pandas as pd

def get_aws_credentials():
    """
    Fetch AWS credentials from environment variables.
    """
    return {
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "aws_session_token": os.getenv("AWS_SESSION_TOKEN")  # Optional for temporary credentials
    }

def set_aws_credentials():
    """
    Set AWS credentials for authentication.
    """
    creds = get_aws_credentials()
    if not creds["aws_access_key_id"] or not creds["aws_secret_access_key"]:
        print("Error: AWS credentials are missing. Please run `aws sso login` or set IAM credentials.")
        exit(1)
    
    os.environ["AWS_ACCESS_KEY_ID"] = creds["aws_access_key_id"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = creds["aws_secret_access_key"]
    if creds["aws_session_token"]:
        os.environ["AWS_SESSION_TOKEN"] = creds["aws_session_token"]

def get_all_namespaces():
    """
    Get all namespaces in the EKS cluster.
    """
    try:
        result = subprocess.run(["kubectl", "get", "namespaces", "-o", "json"], capture_output=True, text=True)
        namespaces = json.loads(result.stdout)
        return [ns["metadata"]["name"] for ns in namespaces["items"]]
    except Exception as e:
        print(f"Error fetching namespaces: {e}")
        return []

def get_pod_image_tags(namespace):
    """
    Get all pod image tags for a given namespace.
    """
    try:
        result = subprocess.run(["kubectl", "get", "pods", "-n", namespace, "-o", "json"], capture_output=True, text=True)
        pods = json.loads(result.stdout)
        image_tags = []

        for pod in pods["items"]:
            pod_name = pod["metadata"]["name"]
            for container in pod["spec"]["containers"]:
                image = container["image"]
                tag = image.split(":")[-1] if ":" in image else "latest"
                image_tags.append({"Namespace": namespace, "Pod": pod_name, "Tag Version": tag})

        return image_tags
    except Exception as e:
        print(f"Error fetching pods in namespace {namespace}: {e}")
        return []

def save_to_excel(data, filename="pod_image_tags.xlsx"):
    """
    Save collected pod image tags to an Excel file.
    """
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

def main():
    """
    Main function to orchestrate the script.
    """
    set_aws_credentials()
    print("AWS credentials set successfully.")

    cluster_name = "idev"
    print(f"Switching to cluster {cluster_name}...")
    subprocess.run(["aws", "eks", "update-kubeconfig", "--name", cluster_name, "--region", "us-west-2"], check=True)

    namespaces = get_all_namespaces()
    if not namespaces:
        print("No namespaces found!")
        return

    all_data = []
    for namespace in namespaces:
        all_data.extend(get_pod_image_tags(namespace))

    if all_data:
        save_to_excel(all_data)
    else:
        print("No data collected.")

if __name__ == "__main__":
    main()
