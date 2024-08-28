import json
import boto3
import os
import subprocess
from jinja2 import Template

accounts = [
    {
        'name': 'dev',
        'region': 'us-west-2'
    },
    {
        'name': 'devB',
        'region': 'us-west-1'
    },
    {
        'name': 'devC',
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

    return pods, namespace_counts

def generate_html_report(clusters_info, current_env):
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EKS Cluster Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #007BFF; color: white; }
            h2 { margin-top: 50px; }
            h1 { color: #007BFF; text-align: center; }
            .download-link { margin-top: 20px; }
            .gauge-container { width: 100px; height: 50px; background: #e6e6e6; border-radius: 5px; position: relative; }
            .gauge-fill { height: 100%; border-radius: 5px; }
            .gauge-label { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; }
            .dropdown { margin-bottom: 10px; }
            .env-selector { margin-bottom: 20px; text-align: center; }
            .pagination { display: flex; justify-content: center; margin-top: 20px; }
            .pagination button { margin: 0 2px; padding: 5px 10px; border: 1px solid #ddd; background-color: #f8f9fa; cursor: pointer; }
            .pagination button:hover { background-color: #007BFF; color: white; }
            .pagination button.disabled { background-color: #e9ecef; cursor: not-allowed; }
        </style>
    </head>
    <body>
        <h1>Welcome to EKS clusters dashboard with VENERABLE</h1>
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

        {% for cluster in clusters %}
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

        <h3>Pods Information by Namespace</h3>
        <div class="dropdown">
            <label for="namespace-select-{{ cluster.name }}">Select Namespace:</label>
            <select id="namespace-select-{{ cluster.name }}" onchange="filterPods(this.value, '{{ cluster.name }}')">
                <option value="">Show All</option>
                {% for namespace in cluster.pods %}
                <option value="{{ namespace }}">{{ namespace }} ({{ cluster.namespace_counts[namespace] }} Pods)</option>
                {% endfor %}
            </select>
        </div>
        <table id="pod-table-{{ cluster.name }}">
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
                <tr class="pod-row" data-namespace="{{ pod.namespace }}">
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
        <div class="dropdown">
            <label for="max-utilization-select-{{ cluster.name }}">Select Metric:</label>
            <select id="max-utilization-select-{{ cluster.name }}" onchange="filterMaxUtilization(this.value, '{{ cluster.name }}')">
                <option value="cpu">Max CPU Utilization</option>
                <option value="memory">Max Memory Utilization</option>
            </select>
        </div>
        <table id="max-utilization-table-{{ cluster.name }}">
            <thead>
                <tr>
                    <th>Namespace</th>
                    <th>Pod Name</th>
                    <th>Node Name</th>
                    <th>CPU Utilization (vCPU)</th>
                    <th>Memory Utilization (GB)</th>
                </tr>
            </thead>
            <tbody id="max-utilization-body-{{ cluster.name }}">
            {% set max_cpu_pods = cluster.pods_info | sort(attribute='cpu_utilization', reverse=True) %}
            {% set max_memory_pods = cluster.pods_info | sort(attribute='memory_utilization_gb', reverse=True) %}
            {% for pod in max_cpu_pods %}
            <tr class="max-cpu-row">
                <td>{{ pod.namespace }}</td>
                <td>{{ pod.name }}</td>
                <td>{{ pod.node_name }}</td>
                <td>{{ pod.cpu_utilization }}</td>
                <td>{{ pod.memory_utilization_gb }}</td>
            </tr>
            {% endfor %}
            {% for pod in max_memory_pods %}
            <tr class="max-memory-row">
                <td>{{ pod.namespace }}</td>
                <td>{{ pod.name }}</td>
                <td>{{ pod.node_name }}</td>
                <td>{{ pod.cpu_utilization }}</td>
                <td>{{ pod.memory_utilization_gb }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
        <div class="pagination" id="pagination-{{ cluster.name }}"></div>
        {% endfor %}

        <a href="eks_report.html" download="eks_report.html" class="download-link">Download Report</a>

        <script>
            const rowsPerPage = 10;

            function changeEnvironment() {
                const envSelect = document.getElementById('env-select');
                const selectedEnv = envSelect.value;
                window.location.href = `?environment=${selectedEnv}`;
            }

            function filterPods(namespace, clusterName) {
                var table = document.getElementById('pod-table-' + clusterName);
                var rows = table.getElementsByClassName('pod-row');
                for (var i = 0; i < rows.length; i++) {
                    var rowNamespace = rows[i].getAttribute('data-namespace');
                    if (namespace === '' || namespace === rowNamespace) {
                        rows[i].style.display = '';
                    } else {
                        rows[i].style.display = 'none';
                    }
                }
            }

            function filterMaxUtilization(metric, clusterName) {
                var maxCpuRows = document.querySelectorAll('#max-utilization-table-' + clusterName + ' .max-cpu-row');
                var maxMemoryRows = document.querySelectorAll('#max-utilization-table-' + clusterName + ' .max-memory-row');

                if (metric === 'cpu') {
                    paginate(maxCpuRows, clusterName);
                } else if (metric === 'memory') {
                    paginate(maxMemoryRows, clusterName);
                }
            }

            function paginate(rows, clusterName) {
                const paginationContainer = document.getElementById('pagination-' + clusterName);
                paginationContainer.innerHTML = '';
                const totalPages = Math.ceil(rows.length / rowsPerPage);
                
                for (let i = 1; i <= totalPages; i++) {
                    const button = document.createElement('button');
                    button.textContent = i;
                    button.addEventListener('click', () => showPage(i, rows));
                    paginationContainer.appendChild(button);
                }

                showPage(1, rows); // Show the first page initially
            }

            function showPage(page, rows) {
                const start = (page - 1) * rowsPerPage;
                const end = start + rowsPerPage;

                for (let i = 0; i < rows.length; i++) {
                    rows[i].style.display = (i >= start && i < end) ? '' : 'none';
                }
            }
        </script>
    </body>
    </html>
    """
    total_clusters = len(clusters_info)
    total_nodes = sum(len(cluster['nodes']) for cluster in clusters_info)
    total_pods = sum(len(cluster['pods_info']) for cluster in clusters_info)
    
    html_template = Template(template)
    html_content = html_template.render(
        total_clusters=total_clusters,
        total_nodes=total_nodes,
        total_pods=total_pods,
        clusters=clusters_info,
        accounts=accounts,
        current_env=current_env
    )

    return html_content

def lambda_handler(event, context):
    # Default to 'dev' environment if not specified
    environment = event.get('queryStringParameters', {}).get('environment', 'dev')
    
    # Set up AWS sessions based on the selected environment
    selected_account = next((acc for acc in accounts if acc['name'] == environment), accounts[0])
    session = get_aws_session(selected_account['region'])
    clusters = get_clusters(session)
    
    clusters_info = []
    for cluster in clusters:
        nodes = get_nodes_and_metrics(cluster, session)
        pods_info, namespace_counts = get_pods_and_metrics(cluster, session)
        clusters_info.append({
            'name': cluster,
            'account': selected_account['name'],
            'region': selected_account['region'],
            'nodes': nodes,
            'pods_info': pods_info,
            'pods': {pod['namespace']: 1 for pod in pods_info},
            'namespace_counts': namespace_counts  # Pass namespace counts to the template
        })

    # Generate the HTML report in real-time
    html_content = generate_html_report(clusters_info, selected_account['name'])

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