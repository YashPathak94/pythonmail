import os
import sys
import boto3
import subprocess
from jinja2 import Template
from datetime import datetime

# Define the different AWS accounts/clusters
accounts = [
    {'name': 'dev', 'region': 'us-east-1'},
    {'name': 'idev', 'region': 'us-east-1'},
    {'name': 'intg', 'region': 'us-east-1'},
    {'name': 'prod', 'region': 'us-east-1'},
    {'name': 'accp', 'region': 'us-east-1'}
]

def set_aws_credentials(environment):
    """
    Dynamically set AWS credentials in the environment for the given environment.
    """
    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
    os.environ['AWS_SESSION_TOKEN'] = os.getenv(f'{environment}_AWS_SESSION_TOKEN')  # Optional

    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
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
        try:
            memory_capacity_gb = int(memory_capacity[:-2]) / 1024  # Convert MiB to GB
        except ValueError:
            memory_capacity_gb = 0

        # Get CPU utilization
        cpu_cmd = f"kubectl top node {node_name} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $2}}'"
        try:
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()
            if cpu_utilization_raw.endswith('m'):
                cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
            else:
                cpu_utilization = float(cpu_utilization_raw) if cpu_utilization_raw.replace('.', '', 1).isdigit() else 0
        except subprocess.CalledProcessError:
            cpu_utilization = 0

        # Get Memory utilization
        memory_cmd = f"kubectl top node {node_name} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $4}}'"
        try:
            memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
            if memory_utilization.endswith('Mi'):
                memory_utilization_gb = int(memory_utilization[:-2]) / 1024  # Convert MiB to GB
            else:
                memory_utilization_gb = float(memory_utilization[:-2]) / 1024 if memory_utilization[:-2].isdigit() else 0
        except subprocess.CalledProcessError:
            memory_utilization_gb = 0

        memory_utilization_percentage = (memory_utilization_gb / memory_capacity_gb) * 100 if memory_capacity_gb > 0 else 0

        nodes.append({
            'name': node_name,
            'cpu_capacity': int(cpu_capacity),
            'memory_capacity_gb': f"{memory_capacity_gb:.2f} GB",
            'cpu_utilization': f"{cpu_utilization:.2f}",
            'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
            'memory_utilization_percentage': f"{memory_utilization_percentage:.2f}"
        })

    return nodes

def get_pods_and_metrics(cluster_name, aws_session, environment):
    pods = []
    namespace_counts = {}
    cmd = f"kubectl get pods --all-namespaces --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} -o jsonpath='{{range .items[*]}}{{.metadata.namespace}}|{{.metadata.name}}|{{.spec.nodeName}} {{end}}'"

    try:
        pod_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl command: {e}")
        return pods, namespace_counts

    for pod in pod_info:
        try:
            namespace, pod_name, node_name = pod.split('|')

            # Determine the namespace group based on suffix
            namespace_group = get_namespace_group(namespace, environment)

            # Increment the namespace count
            if namespace not in namespace_counts:
                namespace_counts[namespace] = 0
            namespace_counts[namespace] += 1

            # Get CPU utilization for the pod
            cpu_cmd = f"kubectl top pod {pod_name} --namespace={namespace} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $2}}'"
            try:
                cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()
                if cpu_utilization_raw.endswith('m'):
                    cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
                else:
                    cpu_utilization = float(cpu_utilization_raw) if cpu_utilization_raw.replace('.', '', 1).isdigit() else 0
            except subprocess.CalledProcessError:
                cpu_utilization = 0

            # Get memory utilization for the pod
            memory_cmd = f"kubectl top pod {pod_name} --namespace={namespace} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $3}}'"
            try:
                memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
                if memory_utilization.endswith('Mi'):
                    memory_utilization_gb = int(memory_utilization[:-2]) / 1024  # Convert MiB to GB
                else:
                    memory_utilization_gb = float(memory_utilization[:-2]) / 1024 if memory_utilization[:-2].isdigit() else 0
            except subprocess.CalledProcessError:
                memory_utilization_gb = 0

            pods.append({
                'namespace': namespace,
                'namespace_group': namespace_group,  # Add namespace group
                'name': pod_name,
                'node_name': node_name,
                'cpu_utilization': f"{cpu_utilization:.2f}",
                'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
            })

        except ValueError as e:
            print(f"Error processing pod in namespace {namespace}: {e}")
            continue

    return pods, namespace_counts

def get_namespace_group(namespace, environment):
    """
    Determine the namespace group based on the suffix and environment.
    """
    suffixes = {
        'dev': ['dev', 'devb', 'devc'],
        'intg': ['intgb', 'intgc'],
        'prod': ['proda', 'prodp'],
        'accp': ['accp', 'accpb', 'accpc'],
        'idev': []  # No suffix
    }
    env_suffixes = suffixes.get(environment, [])
    for suffix in env_suffixes:
        if namespace.endswith(suffix):
            return suffix
    if environment == 'idev':
        return 'idev'  # Single group for idev
    return 'other'  # Fallback group

def group_namespaces_by_suffix(namespaces, env):
    """
    Group namespaces by common suffix based on the environment.
    Handles different suffixes for intg, prod, accp, and dev environments.
    """
    grouped_namespaces = {
        'dev': [], 'devb': [], 'devc': [], 'intgb': [], 'intgc': [],
        'proda': [], 'prodp': [], 'accp': [], 'accpb': [], 'accpc': [],
        'idev': [], 'other': []
    }

    for ns in namespaces:
        if env == 'dev':
            if ns.endswith('dev'):
                grouped_namespaces['dev'].append(ns)
            elif ns.endswith('devb'):
                grouped_namespaces['devb'].append(ns)
            elif ns.endswith('devc'):
                grouped_namespaces['devc'].append(ns)
            else:
                grouped_namespaces['other'].append(ns)
        elif env == 'intg':
            if ns.endswith('intgb'):
                grouped_namespaces['intgb'].append(ns)
            elif ns.endswith('intgc'):
                grouped_namespaces['intgc'].append(ns)
            else:
                grouped_namespaces['other'].append(ns)
        elif env == 'prod':
            if ns.endswith('proda'):
                grouped_namespaces['proda'].append(ns)
            elif ns.endswith('prodp'):
                grouped_namespaces['prodp'].append(ns)
            else:
                grouped_namespaces['other'].append(ns)
        elif env == 'accp':
            if ns.endswith('accp'):
                grouped_namespaces['accp'].append(ns)
            elif ns.endswith('accpb'):
                grouped_namespaces['accpb'].append(ns)
            elif ns.endswith('accpc'):
                grouped_namespaces['accpc'].append(ns)
            else:
                grouped_namespaces['other'].append(ns)
        elif env == 'idev':
            grouped_namespaces['idev'].append(ns)  # idev has no suffix, treat it separately
        else:
            grouped_namespaces['other'].append(ns)

    return grouped_namespaces

# Modify the generate_html_report function to handle different environments and suffixes
def generate_html_report(clusters_info, current_env):
    # Generate a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EKS Cluster Dashboard</title>
        <link rel="icon" type="image/x-icon" href="favicon.ico">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: white;
                color: black;
                transition: all 0.3s ease;
            }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #007BFF; color: white; }
            h2 { margin-top: 50px; }
            h1 { color: #007BFF; text-align: center; }
            p { font-weight: bold; color: black; }
            .dropdown { margin-bottom: 10px; }
            .env-selector { margin-bottom: 20px; text-align: center; font-weight: bold; color: black; }
            #env-select { border: 2px solid black; font-weight: bold; padding: 5px; }
            .footer { text-align: center; margin-top: 50px; font-size: 14px; font-weight: bold; }
            .footer span { color: red; }
            .timestamp { text-align: right; font-size: 14px; color: grey; font-weight: bold; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>Welcome to EKS Clusters Dashboard</h1>

        <div class="timestamp">Report generated on: {{ timestamp }}</div>

        <div class="env-selector">
            <label for="env-select">Select Environment: </label>
            <select id="env-select" onchange="changeEnvironment()">
                {% for account in accounts %}
                <option value="{{ account.name }}" {% if account.name == current_env %}selected{% endif %}>{{ account.name }}</option>
                {% endfor %}
            </select>
        </div>

        <h3>Cluster Summary (Total Nodes & Pods per Cluster)</h3>
        <table>
            <thead>
                <tr>
                    <th>Cluster Name</th>
                    <th>Total Nodes</th>
                    <th>Total Pods</th>
                </tr>
            </thead>
            <tbody>
            {% for cluster in clusters %}
                <tr>
                    <td>{{ cluster.name }} ({{ cluster.account }})</td>
                    <td>{{ cluster.total_nodes }}</td>
                    <td>{{ cluster.total_pods }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        {% for cluster in clusters %}
        <div id="cluster-{{ cluster.account }}" style="display: {% if cluster.account == current_env %}block{% else %}none{% endif %};">
            <h2>{{ cluster.name }} ({{ cluster.account }} - {{ cluster.region }})</h2>

            <h3>Nodes Information</h3>
            <table>
                <thead>
                    <tr>
                        <th>Node Name</th>
                        <th>CPU Capacity (vCPU)</th>
                        <th>Memory Capacity (GB)</th>
                        <th>CPU Utilization (%)</th>
                        <th>Memory Utilization (GB)</th>
                    </tr>
                </thead>
                <tbody>
                {% for node in cluster.nodes %}
                    <tr>
                        <td>{{ node.name }}</td>
                        <td>{{ node.cpu_capacity }}</td>
                        <td>{{ node.memory_capacity_gb }}</td>
                        <td>{{ node.cpu_utilization }}%</td>
                        <td>{{ node.memory_utilization_gb }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>

            <h3>Pods Information by Namespace Group</h3>
            <div class="dropdown">
                <label for="namespace-group-select-{{ cluster.name }}">Select Namespace Group:</label>
                <select id="namespace-group-select-{{ cluster.name }}" onchange="filterPodsByGroup(this.value, '{{ cluster.name }}')">
                    <option value="">Show All</option>
                    {% for group, namespaces in cluster.grouped_namespaces.items() %}
                        <option value="{{ group }}">{{ group }} ({{ namespaces | length }} Namespaces)</option>
                    {% endfor %}
                </select>
            </div>
            <table id="pod-table-{{ cluster.name }}">
                <thead>
                    <tr>
                        <th>Namespace</th>
                        <th>Pod Name</th>
                        <th>Node Name</th>
                        <th>CPU Util
