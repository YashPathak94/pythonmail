import os
import sys
import boto3
import subprocess
from jinja2 import Template
from datetime import datetime

# Define the different AWS accounts/clusters
accounts = [
    {
        'name': 'dev',
        'region': 'us-east-1',
        'environment': 'dev'
    },
    {
        'name': 'idev',
        'region': 'us-east-1',
        'environment': 'idev'
    },
    {
        'name': 'intg',
        'region': 'us-east-1',
        'environment': 'intg'
    },
    {
        'name': 'prod',
        'region': 'us-east-1',
        'environment': 'prod'
    },
    {
        'name': 'dr',
        'region': 'us-west-2',
        'environment': 'dr'
    },
    # Add more accounts as needed
]

# Define suffixes for each environment
suffixes_map = {
    'dev': ['dev', 'devb', 'devc'],
    'intg': ['intg', 'intgb', 'intgc'],
    'prod': ['proda', 'prodb'],
    'accp': ['accp', 'accpb', 'accpc'],
    'idev': [],
    'dr': []
}

def set_aws_credentials(account):
    """
    Dynamically set AWS credentials in the environment for the given account.
    """
    environment = account['environment']
    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
    os.environ['AWS_SESSION_TOKEN'] = os.getenv(f'{environment}_AWS_SESSION_TOKEN', '')

    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        print(f"Warning: AWS credentials for '{account['name']}' are not set correctly.")
        return False

    print(f"Using credentials for environment: '{account['name']}'")
    return True

def get_aws_session(region):
    return boto3.Session(region_name=region)

def get_clusters(aws_session):
    eks_client = aws_session.client('eks')
    try:
        clusters = eks_client.list_clusters()['clusters']
        return clusters
    except Exception as e:
        print(f"Error fetching clusters for region {aws_session.region_name}: {e}")
        return []

def update_kubeconfig(cluster_name, region):
    try:
        env = os.environ.copy()
        cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
        output = subprocess.check_output(cmd, shell=True, env=env).decode('utf-8').strip()
        print(output)
        # Extract the context name from the output
        context_line = [line for line in output.split('\n') if 'Added new context' in line or 'Updated context' in line]
        if context_line:
            context_name = context_line[0].split()[-1]
            print(f"Context name: {context_name}")
            return context_name
        else:
            print("Unable to extract context name from output.")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Error updating kubeconfig for cluster '{cluster_name}': {e.output.decode()}")
        return None

def parse_cpu_utilization(cpu_utilization_raw):
    if cpu_utilization_raw.endswith('m'):
        cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
    else:
        cpu_utilization = int(cpu_utilization_raw) if cpu_utilization_raw.isdigit() else 0
    return cpu_utilization

def parse_memory_utilization(memory_utilization_raw, memory_capacity_gb):
    memory_unit = memory_utilization_raw[-2:]
    memory_value = memory_utilization_raw[:-2]

    if memory_unit == 'Ki':
        memory_utilization_gb = int(memory_value) / (1024 ** 2)
    elif memory_unit == 'Mi':
        memory_utilization_gb = int(memory_value) / 1024
    elif memory_unit == 'Gi':
        memory_utilization_gb = int(memory_value)
    else:
        memory_utilization_gb = int(memory_value) / (1024 ** 3)

    memory_utilization_percentage = (memory_utilization_gb / memory_capacity_gb) * 100 if memory_capacity_gb > 0 else 0

    return memory_utilization_gb, memory_utilization_percentage

def get_nodes_and_metrics(account):
    nodes = []
    try:
        env = os.environ.copy()
        cmd = f"kubectl get nodes --context {account['context']} -o jsonpath='{{range .items[*]}}{{.metadata.name}}|{{.status.capacity.cpu}}|{{.status.capacity.memory}} {{end}}'"
        node_info_output = subprocess.check_output(cmd, shell=True, env=env).decode('utf-8').strip()
        if not node_info_output:
            print(f"No nodes found in cluster '{account['name']}'")
            return nodes

        node_info = node_info_output.split()

        for node in node_info:
            node_details = node.split('|')
            if len(node_details) != 3:
                print(f"Unexpected node data format: {node_details}")
                continue

            node_name, cpu_capacity, memory_capacity = node_details
            memory_capacity_value = memory_capacity[:-2]  # Remove unit
            memory_unit = memory_capacity[-2:]

            # Convert memory capacity to GB
            if memory_unit == 'Ki':
                memory_capacity_gb = int(memory_capacity_value) / (1024 ** 2)
            elif memory_unit == 'Mi':
                memory_capacity_gb = int(memory_capacity_value) / 1024
            elif memory_unit == 'Gi':
                memory_capacity_gb = int(memory_capacity_value)
            else:
                memory_capacity_gb = int(memory_capacity_value) / (1024 ** 3)

            # Get node metrics
            cpu_cmd = f"kubectl top node {node_name} --context {account['context']} --no-headers | awk '{{print $2}}'"
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True, env=env).decode('utf-8').strip()

            memory_cmd = f"kubectl top node {node_name} --context {account['context']} --no-headers | awk '{{print $4}}'"
            memory_utilization_raw = subprocess.check_output(memory_cmd, shell=True, env=env).decode('utf-8').strip()

            # Process CPU utilization
            cpu_utilization = parse_cpu_utilization(cpu_utilization_raw)

            # Process memory utilization
            memory_utilization_gb, memory_utilization_percentage = parse_memory_utilization(memory_utilization_raw, memory_capacity_gb)

            nodes.append({
                'name': node_name,
                'cpu_capacity': cpu_capacity,
                'memory_capacity_gb': f"{memory_capacity_gb:.2f} GB",
                'cpu_utilization': f"{cpu_utilization:.2f}",
                'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
                'memory_utilization_percentage': f"{memory_utilization_percentage:.2f}"
            })

    except subprocess.CalledProcessError as e:
        print(f"Error fetching nodes for cluster '{account['name']}': {e.output.decode()}")

    return nodes

def get_pods_and_metrics(account):
    pods = []
    namespace_counts = {}
    suffixes = suffixes_map.get(account['name'], [])
    if account['name'] == 'idev' or account['name'] == 'dr':
        group_counts = {'total': 0}
        group_order = ['total']
    else:
        group_counts = {suffix: 0 for suffix in suffixes}
        group_counts['others'] = 0
        group_order = suffixes.copy()
        group_order.append('others')

    try:
        env = os.environ.copy()
        cmd = f"kubectl get pods --all-namespaces --context {account['context']} -o jsonpath='{{range .items[*]}}{{.metadata.namespace}}|{{.metadata.name}}|{{.spec.nodeName}} {{end}}'"
        pod_info_output = subprocess.check_output(cmd, shell=True, env=env).decode('utf-8').strip()
        if not pod_info_output:
            print(f"No pods found in cluster '{account['name']}'")
            return pods, namespace_counts, group_counts, group_order

        pod_info = pod_info_output.split()

        for pod in pod_info:
            try:
                namespace, pod_name, node_name = pod.split('|')

                # Increment the namespace count
                namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1

                # Process group counts
                if account['name'] == 'idev' or account['name'] == 'dr':
                    group_counts['total'] += 1
                else:
                    matched = False
                    for suffix in suffixes:
                        if namespace.endswith(suffix):
                            group_counts[suffix] += 1
                            matched = True
                            break
                    if not matched:
                        group_counts['others'] += 1

                # Get pod metrics
                cpu_cmd = f"kubectl top pod {pod_name} --namespace={namespace} --context {account['context']} --no-headers | awk '{{print $2}}'"
                cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True, env=env).decode('utf-8').strip()

                memory_cmd = f"kubectl top pod {pod_name} --namespace={namespace} --context {account['context']} --no-headers | awk '{{print $3}}'"
                memory_utilization_raw = subprocess.check_output(memory_cmd, shell=True, env=env).decode('utf-8').strip()

                # Process CPU utilization
                cpu_utilization = parse_cpu_utilization(cpu_utilization_raw)

                # Process memory utilization
                memory_utilization_gb, _ = parse_memory_utilization(memory_utilization_raw, 1)  # Capacity not used here

                pods.append({
                    'namespace': namespace,
                    'name': pod_name,
                    'node_name': node_name,
                    'cpu_utilization': f"{cpu_utilization:.2f}",
                    'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
                })

            except ValueError as e:
                print(f"Error processing pod data: {pod}. Error: {e}")
                continue

    except subprocess.CalledProcessError as e:
        print(f"Error fetching pods for cluster '{account['name']}': {e.output.decode()}")

    return pods, namespace_counts, group_counts, group_order

def generate_html_report(clusters_info, current_env):
    # Placeholder for HTML report generation logic
    # Replace this with your actual HTML template and rendering code
    html_content = "<html><body><h1>EKS Cluster Report</h1></body></html>"
    return html_content

def main():
    environment = 'dev'

    clusters_info = []

    for account in accounts:
        if not set_aws_credentials(account):
            continue

        session = get_aws_session(account['region'])
        clusters = get_clusters(session)

        for cluster in clusters:
            # Update kubeconfig for the cluster
            context_name = update_kubeconfig(cluster, account['region'])
            if not context_name:
                continue  # Skip this cluster if unable to update kubeconfig

            # Add context to account
            account_copy = account.copy()  # Create a copy to avoid overwriting
            account_copy['context'] = context_name

            # Fetch nodes and pods
            nodes = get_nodes_and_metrics(account_copy)
            pods_info, namespace_counts, group_counts, group_order = get_pods_and_metrics(account_copy)

            clusters_info.append({
                'name': cluster,
                'account': account['name'],
                'region': account['region'],
                'nodes': nodes,
                'pods_info': pods_info,
                'pods': {pod['namespace']: 1 for pod in pods_info},
                'namespace_counts': namespace_counts,
                'group_counts': group_counts,
                'group_order': group_order
            })

    # Generate the HTML report
    html_content = generate_html_report(clusters_info, environment)

    # Output the report or save it to a file
    with open('eks_dashboard.html', 'w') as f:
        f.write(html_content)
    print("Dashboard HTML generated.")

if __name__ == '__main__':
    main()
