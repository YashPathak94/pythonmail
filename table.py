import os
import sys
import boto3
import subprocess
from jinja2 import Template
from datetime import datetime
from collections import defaultdict

# Define the different AWS accounts/clusters
accounts = [
    {'name': 'dev', 'region': 'us-east-1'},
    {'name': 'idev', 'region': 'us-east-1'},
    {'name': 'intg', 'region': 'us-east-1'},
    {'name': 'accp', 'region': 'us-east-1'},
    {'name': 'prod', 'region': 'us-east-1'}
]

env_to_suffix_map = {
    'dev': ['dev', 'devb', 'devc'],
    'intg': ['intg', 'intgb', 'intgc'],
    'accp': ['accp', 'accpb', 'accpc'],
    'prod': ['proda', 'prodb']
}


def set_aws_credentials(environment):
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
    account_id = aws_session.client('sts').get_caller_identity()['Account']
    context = f'arn:aws:eks:{aws_session.region_name}:{account_id}:cluster/{cluster_name}'

    cmd = f"kubectl get nodes --context={context} -o jsonpath='{{{{range .items[*]}}}}{{{{.metadata.name}}}}|{{{{.status.capacity.cpu}}}}|{{{{.status.capacity.memory}}}} {{{{end}}}}'"
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

        cpu_cmd = f"kubectl top node {node_name} --context={context} --no-headers | awk '{{{{print $2}}}}'"
        try:
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()
        except subprocess.CalledProcessError:
            cpu_utilization_raw = '0'

        if cpu_utilization_raw.endswith('m'):
            cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
        else:
            cpu_utilization = int(cpu_utilization_raw) if cpu_utilization_raw.isdigit() else 0

        memory_cmd = f"kubectl top node {node_name} --context={context} --no-headers | awk '{{{{print $4}}}}'"
        try:
            memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
        except subprocess.CalledProcessError:
            memory_utilization = '0Mi'

        memory_utilization_value = memory_utilization[:-2]
        if memory_utilization_value.isdigit():
            memory_utilization_gb = int(memory_utilization_value) / 1024  # Convert MiB to GB
        else:
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


def get_pods_and_metrics(cluster_name, aws_session):
    pods = []
    namespace_counts = {}
    account_id = aws_session.client('sts').get_caller_identity()['Account']
    context = f'arn:aws:eks:{aws_session.region_name}:{account_id}:cluster/{cluster_name}'

    cmd = f"kubectl get pods --all-namespaces --context={context} -o jsonpath='{{{{range .items[*]}}}}{{{{.metadata.namespace}}}}|{{{{.metadata.name}}}}|{{{{.spec.nodeName}}}} {{{{end}}}}'"

    try:
        pod_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl command: {e}")
        return pods, namespace_counts

    for pod in pod_info:
        try:
            namespace, pod_name, node_name = pod.split('|')

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

def count_pods_by_suffixes(namespace_counts, suffixes):
    counts = {suffix: 0 for suffix in suffixes}
    counts['others'] = 0

    for namespace, count in namespace_counts.items():
        matched = False
        for suffix in suffixes:
            if namespace.lower().endswith(suffix.lower()):
                counts[suffix] += count
                matched = True
                break
        if not matched:
            counts['others'] += count
    return counts

def generate_html_report(clusters_info, current_env):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>EKS Cluster Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #007BFF; color: white; }
            h2 { margin-top: 50px; }
            h1 { color: #007BFF; text-align: center; }
            p { font-weight: bold; }
            .footer { text-align: center; margin-top: 50px; font-size: 14px; font-weight: bold; }
            .footer span { color: red; }
            .timestamp { text-align: right; font-size: 14px; color: grey; font-weight: bold; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>EKS Clusters Dashboard</h1>
        <div class="timestamp">Report generated on: {{ timestamp }}</div>
        <p>Total Clusters: {{ total_clusters }}</p>
        <p>Total Nodes: {{ total_nodes }}</p>
        <p>Total Pods: {{ total_pods }}</p>

        {% if current_env != 'idev' %}
        <h3>Total Pods by Namespace Suffix</h3>
        <table>
            <thead>
                <tr>
                    <th>Namespace Suffix</th>
                    <th>Total Pods</th>
                </tr>
            </thead>
            <tbody>
            {% for suffix in suffixes %}
                <tr>
                    <td>{{ suffix }}</td>
                    <td>{{ counts_by_suffix.get(suffix, 0) }}</td>
                </tr>
            {% endfor %}
                <tr>
                    <td>others</td>
                    <td>{{ counts_by_suffix.get('others', 0) }}</td>
                </tr>
            </tbody>
        </table>
        {% else %}
        <p>Total Pods: {{ counts_by_suffix['total_pods'] }}</p>
        {% endif %}

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
            {% for cluster in clusters_in_env %}
                <tr>
                    <td>{{ cluster.name }} ({{ cluster.account }})</td>
                    <td>{{ cluster.total_nodes }}</td>
                    <td>{{ cluster.total_pods }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        {% for cluster in clusters_in_env %}
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

        <h3>Pods Information by Namespace</h3>
        <table>
            <thead>
                <tr>
                    <th>Namespace</th>
                    <th>Pod Name</th>
                    <th>Node Name</th>
                    <th>CPU Utilization (vCPU)</th>
                    <th>Memory Utilization (GB)</th>
                </tr>
            </thead>
            <tbody>
            {% for pod in cluster.pods_info %}
                <tr>
                    <td>{{ pod.namespace }}</td>
                    <td>{{ pod.name }}</td>
                    <td>{{ pod.node_name }}</td>
                    <td>{{ pod.cpu_utilization }}</td>
                    <td>{{ pod.memory_utilization_gb }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        <h3>Maximum Utilization within Cluster</h3>
        <table>
            <thead>
                <tr>
                    <th>Namespace</th>
                    <th>Pod Name</th>
                    <th>Node Name</th>
                    <th>CPU Utilization (vCPU)</th>
                    <th>Memory Utilization (GB)</th>
                </tr>
            </thead>
            <tbody>
                {% set max_cpu_pods = cluster.pods_info | sort(attribute='cpu_utilization', reverse=True)[:5] %}
                {% set max_memory_pods = cluster.pods_info | sort(attribute='memory_utilization_gb', reverse=True)[:5] %}
                {% for pod in max_cpu_pods %}
                <tr>
                    <td>{{ pod.namespace }}</td>
                    <td>{{ pod.name }}</td>
                    <td>{{ pod.node_name }}</td>
                    <td>{{ pod.cpu_utilization }}</td>
                    <td>{{ pod.memory_utilization_gb }}</td>
                </tr>
                {% endfor %}
                {% for pod in max_memory_pods %}
                <tr>
                    <td>{{ pod.namespace }}</td>
                    <td>{{ pod.name }}</td>
                    <td>{{ pod.node_name }}</td>
                    <td>{{ pod.cpu_utilization }}</td>
                    <td>{{ pod.memory_utilization_gb }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endfor %}

        <div class="footer">
            Built with <span>❤️</span>
        </div>

        <script>
            function changeEnvironment() {
                const envSelect = document.getElementById('env-select');
                const selectedEnv = envSelect.value;
                window.location.href = "?environment=" + selectedEnv;
            }
        </script>
    </body>
    </html>
    """

    clusters_in_env = [cluster for cluster in clusters_info if cluster['account'] == current_env]

    aggregated_namespace_counts = defaultdict(int)
    for cluster in clusters_in_env:
        for namespace, count in cluster['namespace_counts'].items():
            aggregated_namespace_counts[namespace] += count

    if current_env != 'idev':
        suffixes = env_to_suffix_map.get(current_env, [])
        counts_by_suffix = count_pods_by_suffixes(aggregated_namespace_counts, suffixes)
    else:
        total_pods = sum(aggregated_namespace_counts.values())
        counts_by_suffix = {'total_pods': total_pods}

    total_clusters = len(clusters_in_env)
    total_nodes = sum(len(cluster['nodes']) for cluster in clusters_in_env)
    total_pods = sum(len(cluster['pods_info']) for cluster in clusters_in_env)

    for cluster in clusters_in_env:
        cluster['total_nodes'] = len(cluster['nodes'])
        cluster['total_pods'] = len(cluster['pods_info'])

    html_template = Template(template)
    html_content = html_template.render(
        timestamp=timestamp,
        total_clusters=total_clusters,
        total_nodes=total_nodes,
        total_pods=total_pods,
        clusters_in_env=clusters_in_env,
        accounts=accounts,
        current_env=current_env,
        counts_by_suffix=counts_by_suffix,
        suffixes=suffixes if current_env != 'idev' else [],
    )

    return html_content


def lambda_handler(event, context):
    environment = event.get('queryStringParameters', {}).get('environment', 'dev')
    clusters_info = []

    for account in accounts:
        if account['name'] != environment:
            continue

        set_aws_credentials(account['name'])
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
                'namespace_counts': namespace_counts
            })

    html_content = generate_html_report(clusters_info, environment)
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': html_content
    }


if __name__ == '__main__':
    event = {'queryStringParameters': {'environment': 'dev'}}
    result = lambda_handler(event, None)
    with open('eks_dashboard.html', 'w') as f:
        f.write(result['body'])
    print("Dashboard HTML generated.")
