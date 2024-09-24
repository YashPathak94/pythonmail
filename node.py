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

def get_instance_type(node_name, aws_session):
    """Retrieve the EC2 instance type for a given node name (Kubernetes node, which is usually EC2 private DNS)."""
    ec2_client = aws_session.client('ec2')
    
    # Attempt to match the EC2 instance using its private DNS name (node_name should match EC2 private DNS)
    try:
        response = ec2_client.describe_instances(
            Filters=[{
                'Name': 'private-dns-name',
                'Values': [node_name]
            }]
        )
        if response['Reservations']:
            instance_type = response['Reservations'][0]['Instances'][0]['InstanceType']
            return instance_type
        else:
            print(f"Warning: No EC2 instance found for node {node_name}.")
            return "Unknown"
    except Exception as e:
        print(f"Error fetching instance type for {node_name}: {e}")
        return "Unknown"

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

        # Fetch the EC2 instance type for this node
        instance_type = get_instance_type(node_name, aws_session)

        # Retrieve CPU and Memory utilization
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
            'instance_type': instance_type,  # Add the instance type to the node information
            'cpu_capacity': int(cpu_capacity),
            'memory_capacity_gb': f"{int(memory_capacity_gb)} GB",
            'cpu_utilization': f"{cpu_utilization:.2f}",
            'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
            'memory_utilization_percentage': f"{memory_utilization_percentage:.2f}"
        })

    return nodes

# Function for generating the HTML report remains the same.
# It will now include the instance_type information in the nodes table.

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
            .gauge-container { width: 100px; height: 50px; background: #e6e6e6; border-radius: 5px; position: relative; }
            .gauge-fill { height: 100%; border-radius: 5px; }
            .gauge-label { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; }
            .dropdown { margin-bottom: 10px; }
            .env-selector { margin-bottom: 20px; text-align: center; font-weight: bold; color: black; }
            #env-select { border: 2px solid black; font-weight: bold; padding: 5px; }
            .footer { text-align: center; margin-top: 50px; font-size: 14px; font-weight: bold; }
            .footer span { color: red; }
            .timestamp { text-align: right; font-size: 14px; color: grey; font-weight: bold; margin-bottom: 20px; }
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

        <!-- Nodes Information -->
        {% for cluster in clusters %}
        <div id="cluster-{{ cluster.account }}" style="display: {% if cluster.account == current_env %}block{% else %}none{% endif %};">
        <h2>{{ cluster.name }} ({{ cluster.account }} - {{ cluster.region }})</h2>

        <h3>Nodes Information</h3>
        <table>
            <thead>
                <tr>
                    <th>Node Name</th>
                    <th>Instance Type</th>
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
                    <td>{{ node.instance_type }}</td> <!-- Added Instance Type column -->
                    <td>{{ node.cpu_capacity }}</td>
                    <td>{{ node.memory_capacity_gb }}</td>
                    <td>{{ node.cpu_utilization }}%</td>
                    <td>{{ node.memory_utilization_gb }}</td>
                    <td>
                        <div class="gauge-container">
                            <div class="gauge-fill" style="width: {{ node.memory_utilization_percentage }}%; background: {% if node.memory_utilization_percentage|float < 75 %}green{% else %}orange{% endif %};"></div>
                            <div class="gauge-label">{{ node.memory_utilization_percentage }}%</div>
                        </div>
                    </td>
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

    # Add per-cluster total nodes and total pods
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
        timestamp=timestamp  # Pass the timestamp to the template
    )

    return html_content
