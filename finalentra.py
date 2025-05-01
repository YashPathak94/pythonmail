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
        'region': 'us-east-1'
    },
    {
        'name': 'idev',
        'region': 'us-east-1'
    },
    {
        'name': 'intg',
        'region': 'us-east-1'
    },
    # Add more accounts as needed
]

# Define suffixes for each environment
suffixes_map = {
    'dev': ['dev', 'devb', 'devc'],
    'intg': ['intg', 'intgb', 'intgc'],
    'prod': ['proda', 'prodb'],
    'accp': ['accp', 'accpb', 'accpc'],
    'idev': []
}

def set_aws_credentials(environment):
    """
    Dynamically set AWS credentials in the environment for the given environment.
    """
    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
    os.environ['AWS_SESSION_TOKEN'] = os.getenv(f'{environment}_AWS_SESSION_TOKEN')  # Optional

    if not os.environ['AWS_ACCESS_KEY_ID'] or not os.environ['AWS_SECRET_ACCESS_KEY']:
        print(f"Error: AWS credentials for {environment} are not set correctly.")
        sys.exit(1)

    print(f"Using credentials for environment: {environment}")

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

def get_nodes_and_metrics(cluster_name, aws_session):
    nodes = []
    cmd = f"kubectl get nodes --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} -o jsonpath='{{range .items[*]}}{{.metadata.name}}|{{.status.capacity.cpu}}|{{.status.capacity.memory}} {{end}}'"
    
    try:
        node_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl command: {e}")
        return nodes

    for node in node_info:
        node_details = node.split('|')
        if len(node_details) != 3:
            print(f"Unexpected node data format: {node_details}")
            continue

        node_name, cpu_capacity, memory_capacity = node_details
        memory_capacity_gb = int(memory_capacity[:-2]) / 1024  # Convert MiB to GB

        cpu_cmd = f"kubectl top node {node_name} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $2}}'"
        cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()

        if cpu_utilization_raw.endswith('m'):
            cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
        else:
            cpu_utilization = int(cpu_utilization_raw) if cpu_utilization_raw.isdigit() else 0

        memory_cmd = f"kubectl top node {node_name} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $4}}'"
        memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
        memory_utilization_gb = int(memory_utilization[:-2]) / 1024 if memory_utilization[:-2].isdigit() else 0  # Convert MiB to GB

        memory_utilization_percentage = (memory_utilization_gb / memory_capacity_gb) * 100 if memory_capacity_gb > 0 else 0

        nodes.append({
            'name': node_name,
            'cpu_capacity': int(cpu_capacity),
            'memory_capacity_gb': f"{int(memory_capacity_gb)} GB",
            'cpu_utilization': f"{cpu_utilization:.2f}",
            'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
            'memory_utilization_percentage': f"{memory_utilization_percentage:.2f}"
        })

    return nodes

def get_pods_and_metrics(cluster_name, aws_session, environment):
    pods = []
    namespace_counts = {}
    suffixes = suffixes_map.get(environment, [])
    if environment == 'idev':
        group_counts = {'total': 0}
        group_order = ['total']
    else:
        group_counts = {suffix: 0 for suffix in suffixes}
        group_counts['others'] = 0
        group_order = suffixes.copy()
        group_order.append('others')

    cmd = f"kubectl get pods --all-namespaces --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} -o jsonpath='{{range .items[*]}}{{.metadata.namespace}}|{{.metadata.name}}|{{.spec.nodeName}} {{end}}'"
    try:
        pod_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl command: {e}")
        return pods, namespace_counts, group_counts, group_order

    for pod in pod_info:
        try:
            namespace, pod_name, node_name = pod.split('|')

            # Increment the namespace count
            namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1

            # Process group counts
            if environment == 'idev':
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

            # Get CPU utilization for the pod
            cpu_cmd = f"kubectl top pod {pod_name} --namespace={namespace} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $2}}'"
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()

            if not cpu_utilization_raw:
                print(f"Warning: No CPU utilization data for pod {pod_name} in namespace {namespace}. Skipping this pod.")
                continue

            if cpu_utilization_raw.endswith('m'):
                cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
            else:
                cpu_utilization = int(cpu_utilization_raw) if cpu_utilization_raw.isdigit() else 0

            # Get memory utilization for the pod
            memory_cmd = f"kubectl top pod {pod_name} --namespace={namespace} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $3}}'"
            memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()

            if not memory_utilization:
                print(f"Warning: No memory utilization data for pod {pod_name} in namespace {namespace}. Skipping this pod.")
                continue

            memory_utilization_gb = int(memory_utilization[:-2]) / 1024 if memory_utilization[:-2].isdigit() else 0  # Convert MiB to GB

            pods.append({
                'namespace': namespace,
                'name': pod_name,
                'node_name': node_name,
                'cpu_utilization': f"{cpu_utilization:.2f}",
                'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
            })

        except ValueError as e:
            print(f"Error processing pod in namespace {namespace}: {e}")
            continue

    return pods, namespace_counts, group_counts, group_order
