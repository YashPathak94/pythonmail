import subprocess
import pandas as pd
import os

# Set AWS credentials
AWS_ACCESS_KEY = "your-access-key"
AWS_SECRET_KEY = "your-secret-key"
AWS_SESSION_TOKEN = "your-session-token"
EKS_CLUSTER = "your-dev-cluster-name"
REGION = "your-cluster-region"

# Set environment variables for AWS authentication
os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY
os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_KEY
os.environ["AWS_SESSION_TOKEN"] = AWS_SESSION_TOKEN
os.environ["AWS_DEFAULT_REGION"] = REGION

# Authenticate with the EKS cluster
subprocess.run(f"aws eks update-kubeconfig --region {REGION} --name {EKS_CLUSTER}", shell=True, check=True)

# Get all namespaces excluding system ones
excluded_namespaces = ["kube-system", "kube-public", "kube-node-lease"]
namespace_cmd = "kubectl get ns --no-headers -o custom-columns=':metadata.name'"
namespace_output = subprocess.run(namespace_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
all_namespaces = namespace_output.stdout.splitlines()
filtered_namespaces = [ns for ns in all_namespaces if ns not in excluded_namespaces]

data = []

# Loop through each namespace and get pod details
for namespace in filtered_namespaces:
    cmd = f"kubectl get pods -n {namespace} -o jsonpath='{{range .items[*]}}{namespace}{{\" \"}}{{.metadata.name}}{{\" \"}}{{range .spec.containers[*]}}{{.image}}{{\"\\n\"}}{{end}}{{end}}'"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            parts = line.split(" ")
            if len(parts) >= 3:
                ns, pod_name, image = parts[0], parts[1], " ".join(parts[2:])
                tag_version = image.split(":")[-1] if ":" in image else "latest"
                data.append([ns, pod_name, tag_version])

# Create a DataFrame and save to Excel
df = pd.DataFrame(data, columns=["Namespace", "Pod Name", "Tag Version"])
output_file = "pod_image_tags.xlsx"
df.to_excel(output_file, index=False)

print(f"Excel file '{output_file}' generated successfully.")

