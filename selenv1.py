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
        return pods

    for pod in pod_info:
        try:
            namespace, pod_name, node_name = pod.split('|')

            # Increment the namespace count
            if namespace not in namespace_counts:
                namespace_counts[namespace] = 0
            namespace_counts[namespace] += 1

            # Add the pod info
            pods.append({
                'namespace': namespace,
                'name': pod_name,
                'node_name': node_name
            })

        except ValueError as e:
            print(f"Error processing pod in namespace {namespace}: {e}")
            continue

    return pods, namespace_counts

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
            .download-link { margin-top: 20px; }
            .env-selector { margin-bottom: 20px; text-align: center; font-weight: bold; color: black; }
            #env-select { border: 2px solid black; font-weight: bold; padding: 5px; }
            .footer { text-align: center; margin-top: 50px; font-size: 14px; font-weight: bold; }
            .footer span { color: red; }
            .timestamp { text-align: right; font-size: 12px; color: grey; font-weight: bold; margin-bottom: 20px; }
            .cluster-summary { margin-bottom: 30px; }
            .cluster-summary th { background-color: #4CAF50; color: white; }
        </style>
    </head>
    <body>
        <h1>Welcome to EKS Clusters Dashboard with VENERABLE</h1>
        <div class="timestamp">Report generated on: {{ timestamp }}</div>

        <div class="env-selector">
            <label for="env-select">Select Environment: </label>
            <select id="env-select" onchange="changeEnvironment()">
                {% for account in accounts %}
                <option value="{{ account.name }}" {% if account.name == current_env %}selected{% endif %}>{{ account.name }}</option>
                {% endfor %}
            </select>
        </div>

        <p>Total Clusters: {{ total_clusters }}</p>
        <p>Total Nodes: {{ total_nodes }}</p>
        <p>Total Pods: {{ total_pods }}</p>

        <!-- Second table to show per-cluster total nodes and pods -->
        <h2>Cluster Summary (Total Nodes & Pods per Cluster)</h2>
        <table class="cluster-summary">
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

        <!-- Existing table for node details -->
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
                    <th>Memory Utilization (%)</th>
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
                    <td>{{ node.memory_utilization_percentage }}%</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        <h3>Pods Information</h3>
        <table>
            <thead>
                <tr>
                    <th>Namespace</th>
                    <th>Pod Name</th>
                    <th>Node Name</th>
                </tr>
            </thead>
            <tbody>
            {% for pod in cluster.pods_info %}
                <tr>
                    <td>{{ pod.namespace }}</td>
                    <td>{{ pod.name }}</td>
                    <td>{{ pod.node_name }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>
        {% endfor %}

        <div class="footer">
            Build with <span>❤️</span> VENERABLE
        </div>

        <script>
            function changeEnvironment() {
                const envSelect = document.getElementById('env-select');
                const selectedEnv = envSelect.value;

                // Hide all clusters
                {% for account in accounts %}
                document.getElementById('cluster-{{ account.name }}').style.display = 'none';
                {% endfor %}
                
                // Show the selected cluster
                document.getElementById('cluster-' + selectedEnv).style.display = 'block';
            }
        </script>
    </body>
    </html>
    """

    total_clusters = len(clusters_info)
    total_nodes = sum(len(cluster['nodes']) for cluster in clusters_info)
    total_pods = sum(len(cluster['pods_info']) for cluster in clusters_info)
    
    # Add total nodes and pods per cluster
    for cluster in clusters_info:
        cluster['total_nodes'] = len(cluster['nodes'])
        cluster['total_pods'] = len(cluster['pods_info'])

    html_template = Template(template)
    html_content = html_template.render(
        total_clusters=total_clusters,
        total_nodes=total_nodes,
        total_pods=total_pods,
        clusters=clusters_info,
        accounts=accounts,
        current_env=current_env,
        timestamp=timestamp
    )

    return html_content

def lambda_handler(event, context):
    # Default to 'dev' environment if not specified
    environment = event.get('queryStringParameters', {}).get('environment', 'dev')
    
    clusters_info = []

    for account in accounts:
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
                'pods': {pod['namespace']: 1 for pod in pods_info},
                'namespace_counts': namespace_counts  # Pass namespace counts to the template
            })

    # Generate the HTML report in real-time
        html_content = generate_html_report(clusters_info, environment)

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
            'environment': 'dev'  # Default to 'dev'
        }
    }
    result = lambda_handler(event, None)
    with open('eks_dashboard.html', 'w') as f:
        f.write(result['body'])
    print("Dashboard HTML generated.")

