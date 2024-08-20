import boto3
from botocore.exceptions import ClientError
from jinja2 import Template
import os
import subprocess

# Define AWS regions for different accounts (assumes credentials are set in environment variables)
accounts = [
    {
        'name': 'Account 1',
        'region': 'us-west-1'
    },
    {
        'name': 'Account 2',
        'region': 'us-east-1'
    },
    # Add more accounts as needed
]

def get_aws_session(region):
    return boto3.Session(region_name=region)

def get_clusters(aws_session):
    eks_client = aws_session.client('eks')
    try:
        clusters = eks_client.list_clusters()['clusters']
        return clusters
    except ClientError as e:
        print(f"Error fetching clusters for region {aws_session.region_name}: {e}")
        return []

def get_nodes_and_metrics(cluster_name, aws_session):
    nodes = []
    # Get node information
    cmd = f"kubectl get nodes --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} -o jsonpath='{{range .items[*]}}{{.metadata.name}}|{{.metadata.labels.kubernetes\\.io/instance-type}}|{{.status.capacity.cpu}}|{{.status.capacity.memory}} {{end}}'"
    node_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()

    # Get node utilization metrics
    for node in node_info:
        node_name, instance_type, cpu_capacity, memory_capacity = node.split('|')
        memory_capacity_gb = int(memory_capacity[:-2]) / 1024  # Convert MiB to GB
        
        # Get CPU utilization
        cpu_cmd = f"kubectl top node {node_name} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $2}}'"
        cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()

        # Convert CPU utilization to cores
        if cpu_utilization_raw.endswith('m'):
            cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000  # Convert millicores to cores
        else:
            cpu_utilization = int(cpu_utilization_raw)  # It's already in cores

        # Get memory utilization
        memory_cmd = f"kubectl top node {node_name} --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | awk '{{print $4}}'"
        memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
        memory_utilization_gb = int(memory_utilization[:-2]) / 1024  # Convert MiB to GB
        
        memory_utilization_percentage = (memory_utilization_gb / memory_capacity_gb) * 100
        
        nodes.append({
            'name': node_name,
            'instance_type': instance_type,
            'cpu_capacity': int(cpu_capacity),
            'memory_capacity_gb': f"{int(memory_capacity_gb)} GB",
            'cpu_utilization': f"{cpu_utilization:.2f}",  # Format to two decimal places
            'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
            'memory_utilization_percentage': f"{memory_utilization_percentage:.2f}"
        })

    return nodes


def get_pods(cluster_name, aws_session):
    namespaces = {}
    cmd = f"kubectl get pods --all-namespaces --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} -o jsonpath='{{range .items[*]}}{{.metadata.namespace}} {{end}}'"
    pod_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    
    for namespace in pod_info:
        if namespace in namespaces:
            namespaces[namespace] += 1
        else:
            namespaces[namespace] = 1
    
    return namespaces

def generate_html_report(clusters_info):
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EKS Cluster Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #007BFF; color: white; }
            h2 { margin-top: 50px; }
            .download-link { margin-top: 20px; }
            .gauge-container { width: 100px; height: 50px; background: #e6e6e6; border-radius: 5px; position: relative; }
            .gauge-fill { height: 100%; border-radius: 5px; }
            .gauge-label { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; }
            .dropdown { margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <h1>EKS Cluster Report</h1>
        <p>Total Clusters: {{ total_clusters }}</p>
        <p>Total Nodes: {{ total_nodes }}</p>
        <p>Total Pods: {{ total_pods }}</p>

        {% for cluster in clusters %}
        <h2>{{ cluster.name }} ({{ cluster.account }} - {{ cluster.region }})</h2>
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
                    <td>{{ node.instance_type }}</td>
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

        <h3>Pods by Namespace</h3>
        <div class="dropdown">
            <label for="namespace-select">Select Namespace:</label>
            <select id="namespace-select" onchange="filterTable(this.value, '{{ cluster.name }}')">
                <option value="">Show All</option>
                {% for namespace in cluster.pods %}
                <option value="{{ namespace }}">{{ namespace }}</option>
                {% endfor %}
            </select>
        </div>
        <table id="pod-table-{{ cluster.name }}">
            <thead>
                <tr>
                    <th>Namespace</th>
                    <th>Total Pods</th>
                </tr>
            </thead>
            <tbody>
            {% for namespace, pod_count in cluster.pods.items() %}
                <tr class="namespace-row" data-namespace="{{ namespace }}">
                    <td>{{ namespace }}</td>
                    <td>{{ pod_count }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        {% endfor %}

        <a href="eks_report.html" download="eks_report.html" class="download-link">Download Report</a>

        <script>
            function filterTable(namespace, clusterName) {
                var table = document.getElementById('pod-table-' + clusterName);
                var rows = table.getElementsByClassName('namespace-row');
                for (var i = 0; i < rows.length; i++) {
                    var rowNamespace = rows[i].getAttribute('data-namespace');
                    if (namespace === '' || namespace === rowNamespace) {
                        rows[i].style.display = '';
                    } else {
                        rows[i].style.display = 'none';
                    }
                }
            }
        </script>
    </body>
    </html>
    """
    total_clusters = len(clusters_info)
    total_nodes = sum(len(cluster['nodes']) for cluster in clusters_info)
    total_pods = sum(sum(namespace.values()) for cluster in clusters_info for namespace in [cluster['pods']])
    
    html_template = Template(template)
    html_content = html_template.render(
        total_clusters=total_clusters,
        total_nodes=total_nodes,
        total_pods=total_pods,
        clusters=clusters_info
    )

    with open("eks_report.html", "w") as file:
        file.write(html_content)

def main():
    clusters_info = []

    for account in accounts:
        session = get_aws_session(account)
        clusters = get_clusters(session)

        for cluster in clusters:
            nodes = get_nodes_and_metrics(cluster, session)
            pods = get_pods(cluster, session)
            clusters_info.append({
                'name': cluster,
                'account': account['name'],
                'region': account['region'],
                'nodes': nodes,
                'pods': pods
            })

    generate_html_report(clusters_info)
    print("EKS report generated: eks_report.html")

if __name__ == '__main__':
    main()
