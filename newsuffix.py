import os
import sys
import boto3
import subprocess
from jinja2 import Template
from datetime import datetime

# Define the different AWS accounts/environments
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
    'dev': ['dev', 'devb', 'devc'],
    'intg': ['intg', 'intgb', 'intgc'],
    'accp': ['accp', 'accpb', 'accpc'],
    'prod': ['proda', 'prodb']
}

def set_aws_credentials(environment):
    """
    Dynamically set AWS credentials in the environment for the given environment.
    """
    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment.upper()}_AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment.upper()}_AWS_SECRET_ACCESS_KEY')
    os.environ['AWS_SESSION_TOKEN'] = os.getenv(f'{environment.upper()}_AWS_SESSION_TOKEN')  # Optional

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
    account_id = aws_session.client('sts').get_caller_identity()['Account']
    context = f"arn:aws:eks:{aws_session.region_name}:{account_id}:cluster/{cluster_name}"
    cmd = f"kubectl get nodes --context={context} -o jsonpath='{{range .items[*]}}{{.metadata.name}}|{{.status.capacity.cpu}}|{{.status.capacity.memory}} {{end}}'"

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

        cpu_cmd = f"kubectl top node {node_name} --context={context} --no-headers | awk '{{print $2}}'"
        try:
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()
            if cpu_utilization_raw.endswith('m'):
                cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
            else:
                cpu_utilization = int(cpu_utilization_raw) if cpu_utilization_raw.isdigit() else 0
        except subprocess.CalledProcessError:
            cpu_utilization = 0

        memory_cmd = f"kubectl top node {node_name} --context={context} --no-headers | awk '{{print $4}}'"
        try:
            memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
            memory_utilization_gb = int(memory_utilization[:-2]) / 1024 if memory_utilization[:-2].isdigit() else 0  # Convert MiB to GB
        except subprocess.CalledProcessError:
            memory_utilization_gb = 0

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
    account_id = aws_session.client('sts').get_caller_identity()['Account']
    context = f"arn:aws:eks:{aws_session.region_name}:{account_id}:cluster/{cluster_name}"
    cmd = f"kubectl get pods --all-namespaces --context={context} -o jsonpath='{{range .items[*]}}{{.metadata.namespace}}|{{.metadata.name}}|{{.spec.nodeName}} {{end}}'"

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
            print(f"Error processing pod: {e}")
            continue

    return pods, namespace_counts

def count_pods_by_suffix(pods_info, selected_suffix):
    """
    Count total number of pods for namespaces that end with a given suffix.
    """
    total_pods = 0
    for pod in pods_info:
        namespace = pod['namespace']
        if namespace.endswith(selected_suffix):
            total_pods += 1
    return total_pods

def generate_html_report(clusters_info, current_env, selected_suffix):
    # Generate a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Generate the HTML template
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <!-- [Head content omitted for brevity, same as before] -->
        <title>EKS Cluster Dashboard</title>
        <style>
            /* [Styles omitted for brevity, same as before] */
        </style>
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

        <p>Total Clusters: {{ total_clusters }}</p>
        <p>Total Nodes: {{ total_nodes }}</p>
        <p>Total Pods: {{ total_pods }}</p>
        <p>Total Pods in namespaces ending with "{{ selected_suffix }}": {{ total_pods_suffix }}</p>

        <!-- [Rest of the HTML content remains the same, including clusters data tables] -->

        <script>
            function changeEnvironment() {
                const envSelect = document.getElementById('env-select');
                const selectedEnv = envSelect.value;
                window.location.href = `?environment=${selectedEnv}`;
            }

            function changeSuffix() {
                const suffixSelect = document.getElementById('suffix-select');
                const selectedSuffix = suffixSelect.value;
                const envSelect = document.getElementById('env-select');
                const selectedEnv = envSelect.value;
                window.location.href = `?environment=${selectedEnv}&suffix=${selectedSuffix}`;
            }

            // [JavaScript functions for filtering pods and max utilization remain the same]
        </script>
    </body>
    </html>
    """

    # Calculate the total number of pods for the selected suffix
    total_pods_suffix = sum(
        count_pods_by_suffix(cluster['pods_info'], selected_suffix) for cluster in clusters_info
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
    environment = event.get('queryStringParameters', {}).get('environment', 'dev').lower()
    suffix = event.get('queryStringParameters', {}).get('suffix')

    # Ensure environment is valid
    if environment not in env_to_suffix_map:
        environment = 'dev'

    # If suffix is not provided or not valid for the environment, default to first suffix
    valid_suffixes = env_to_suffix_map[environment]
    if not suffix or suffix not in valid_suffixes:
        suffix = valid_suffixes[0]

    clusters_info = []

    # Find the account that matches the selected environment
    account = next((acc for acc in accounts if acc['name'] == environment), None)
    if account:
        # Set AWS credentials for the current environment
        set_aws_credentials(account['name'])

        # Set up AWS session based on the selected environment
        session = get_aws_session(account['region'])
        clusters = get_clusters(session)

        for cluster in clusters:
            nodes = get_nodes_and_metrics(cluster, session)
            pods_info, namespace_counts = get_pods_and_metrics(cluster, session)

            # Filter pods based on the selected suffix
            filtered_pods_info = [pod for pod in pods_info if pod['namespace'].endswith(suffix)]

            clusters_info.append({
                'name': cluster,
                'account': account['name'],
                'region': account['region'],
                'nodes': nodes,
                'pods_info': pods_info,  # All pods info
                'filtered_pods_info': filtered_pods_info,  # Pods matching the selected suffix
                'namespace_counts': namespace_counts  # All namespace counts
            })

    else:
        print(f"No account found for environment: {environment}")
        sys.exit(1)

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
