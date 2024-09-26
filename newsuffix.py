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
        'name': 'intg',
        'region': 'us-east-1'
    },
    {
        'name': 'accp',
        'region': 'us-east-1'
    },
    {
        'name': 'prod',
        'region': 'us-east-1'
    },
    # Add more accounts as needed
]

# Map environments to their corresponding suffixes
env_to_suffix_map = {
    'dev': ['dev', 'devB', 'devC'],
    'intg': ['intg', 'intgB', 'intgC'],
    'accp': ['accp', 'accpB', 'accpC'],
    'prod': ['prodA', 'prodB']
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

def get_pods_and_metrics(cluster_name, aws_session):
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

            # Increment the namespace count
            if namespace not in namespace_counts:
                namespace_counts[namespace] = 0
            namespace_counts[namespace] += 1

            pods.append({
                'namespace': namespace,
                'name': pod_name,
                'node_name': node_name,
            })

        except ValueError as e:
            print(f"Error processing pod in namespace {namespace}: {e}")
            continue

    return pods, namespace_counts

def count_pods_by_suffix(namespace_counts, suffix):
    """
    Count total number of pods for namespaces that end with a given suffix.
    """
    total_pods = 0
    for namespace, count in namespace_counts.items():
        if namespace.endswith(suffix):
            total_pods += count
    return total_pods

def generate_html_report(clusters_info, current_env, selected_suffix):
    # Generate a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Generate the HTML template
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <!-- ... [Same as before, omitted for brevity] ... -->
    </head>
    <body>
        <h1>Welcome to EKS Clusters Dashboard with VENERABLE</h1>

        <div class="timestamp">Report generated on: {{ timestamp }}</div>

        <div class="env-selector">
            <label for="env-select">Select Environment: </label>
            <select id="env-select" onchange="changeEnvironment()">
                {% for env in environments %}
                <option value="{{ env }}" {% if env == current_env %}selected{% endif %}>{{ env }}</option>
                {% endfor %}
            </select>
        </div>

        <div class="env-selector">
            <label for="suffix-select">Select Namespace Suffix: </label>
            <select id="suffix-select" onchange="changeSuffix()">
                {% for suffix in env_to_suffix_map[current_env] %}
                <option value="{{ suffix }}" {% if suffix == selected_suffix %}selected{% endif %}>{{ suffix }}</option>
                {% endfor %}
            </select>
        </div>

        <!-- ... [Rest of the HTML template remains the same] ... -->
    </body>
    </html>
    """

    # Calculate the total number of pods for the selected suffix
    total_pods_suffix = sum(
        count_pods_by_suffix(cluster['namespace_counts'], selected_suffix) for cluster in clusters_info
    )

    total_clusters = len(clusters_info)
    total_nodes = sum(len(cluster['nodes']) for cluster in clusters_info)
    total_pods = sum(len(cluster['pods_info']) for cluster in clusters_info)

    # Add per-cluster total nodes and total pods
    for cluster in clusters_info:
        cluster['total_nodes'] = len(cluster['nodes'])
        cluster['total_pods'] = len(cluster['pods_info'])

    # Prepare environments list for the template
    environments = list(env_to_suffix_map.keys())

    html_template = Template(template)
    html_content = html_template.render(
        total_clusters=total_clusters,
        total_nodes=total_nodes,
        total_pods_suffix=total_pods_suffix,
        total_pods=total_pods,
        clusters=clusters_info,
        environments=environments,
        current_env=current_env,
        selected_suffix=selected_suffix,
        env_to_suffix_map=env_to_suffix_map,
        timestamp=timestamp
    )

    return html_content

def lambda_handler(event, context):
    # Default to 'dev' environment and first suffix if not specified
    environment = event.get('queryStringParameters', {}).get('environment', 'dev')
    suffix = event.get('queryStringParameters', {}).get('suffix')

    # Ensure environment is valid
    if environment not in env_to_suffix_map:
        environment = 'dev'

    # If suffix is not provided or not valid for the environment, default to first suffix
    valid_suffixes = env_to_suffix_map[environment]
    if not suffix or suffix not in valid_suffixes:
        suffix = valid_suffixes[0]

    clusters_info = []

    for account in accounts:
        if account['name'] == environment:
            # Set AWS credentials for the current environment
            set_aws_credentials(account['name'])

            # Set up AWS sessions based on the selected environment
            session = get_aws_session(account['region'])
            clusters = get_clusters(session)

            for cluster in clusters:
                nodes = get_nodes_and_metrics(cluster, session)
                pods_info, namespace_counts = get_pods_and_metrics(cluster, session)
                clusters_info.append({
                    'name': cluster,
                    'account': account['name'],
                    'region': account['region'],
                    'nodes': nodes,
                    'pods_info': pods_info,
                    'namespace_counts': namespace_counts  # Pass namespace counts to the template
                })

    # Generate the HTML report in real-time
    html_content = generate_html_report(clusters_info, environment, suffix)

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/html',
        },
        'body': html_content
    }

if __name__ == '__main__':
    # Simulate a request for local testing
    event = {
        'queryStringParameters': {
            'environment': 'dev',  # Default to 'dev'
            'suffix': 'dev'  # Default to 'dev'
        }
    }
    result = lambda_handler(event, None)
    with open('eks_dashboard.html', 'w') as f:
        f.write(result['body'])
    print("Dashboard HTML generated.")
