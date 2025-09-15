import os
import sys
import boto3
import subprocess
from jinja2 import Template
from datetime import datetime

# Define the different AWS accounts/clusters
accounts = [
    {'name': 'dev',  'region': 'us-east-1'},
    {'name': 'idev', 'region': 'us-east-1'},
    {'name': 'intg', 'region': 'us-east-1'},
    # Add more accounts as needed
]

# Define suffixes for each environment
suffixes_map = {
    'dev':  ['dev', 'devb', 'devc'],
    'intg': ['intg', 'intgb', 'intgc'],
    'prod': ['proda', 'prodb'],
    'accp': ['accp', 'accpb', 'accpc'],
    'idev': []  # idev is treated as a single bucket
}

def set_aws_credentials(environment):
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

def _kubectl_ctx(aws_session, cluster_name):
    account_id = aws_session.client('sts').get_caller_identity()['Account']
    return f"arn:aws:eks:{aws_session.region_name}:{account_id}:cluster/{cluster_name}"

def get_nodes_and_metrics(cluster_name, aws_session):
    nodes = []
    ctx = _kubectl_ctx(aws_session, cluster_name)
    cmd = (
        f"kubectl get nodes --context={ctx} "
        "-o jsonpath='{range .items[*]}{.metadata.name}|{.status.capacity.cpu}|{.status.capacity.memory} {end}'"
    )
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
        # memory capacity is usually Mi: e.g. "163840Mi"
        try:
            mem_val = int(memory_capacity[:-2])  # drop "Mi"
        except Exception:
            mem_val = 0
        memory_capacity_gb = mem_val / 1024.0

        cpu_cmd = (
            f"kubectl top node {node_name} --context={ctx} --no-headers | awk '{{print $2}}'"
        )
        cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()

        if cpu_utilization_raw.endswith('m'):
            try:
                cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000.0  # millicores->cores
            except Exception:
                cpu_utilization = 0.0
        else:
            cpu_utilization = float(cpu_utilization_raw) if cpu_utilization_raw else 0.0

        memory_cmd = (
            f"kubectl top node {node_name} --context={ctx} --no-headers | awk '{{print $4}}'"
        )
        memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
        # "XXXXMi"
        try:
            memory_utilization_gb = (int(memory_utilization[:-2]) / 1024.0) if memory_utilization.endswith('Mi') else 0.0
        except Exception:
            memory_utilization_gb = 0.0

        memory_utilization_percentage = (memory_utilization_gb / memory_capacity_gb * 100.0) if memory_capacity_gb > 0 else 0.0

        nodes.append({
            'name': node_name,
            'cpu_capacity': int(cpu_capacity) if cpu_capacity.isdigit() else cpu_capacity,
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

    ctx = _kubectl_ctx(aws_session, cluster_name)
    cmd = (
        f"kubectl get pods --all-namespaces --context={ctx} "
        "-o jsonpath='{range .items[*]}{.metadata.namespace}|{.metadata.name}|{.spec.nodeName} {end}'"
    )
    try:
        pod_info = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl command: {e}")
        return pods, namespace_counts, group_counts, group_order

    for pod in pod_info:
        try:
            namespace, pod_name, node_name = pod.split('|')
            namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1

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

            cpu_cmd = (
                f"kubectl top pod {pod_name} --namespace={namespace} --context={ctx} --no-headers | awk '{{print $2}}'"
            )
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8').strip()
            if not cpu_utilization_raw:
                # skip pods that have no metrics yet
                continue

            if cpu_utilization_raw.endswith('m'):
                cpu_utilization = int(cpu_utilization_raw[:-1]) / 1000.0
            else:
                cpu_utilization = float(cpu_utilization_raw) if cpu_utilization_raw else 0.0

            memory_cmd = (
                f"kubectl top pod {pod_name} --namespace={namespace} --context={ctx} --no-headers | awk '{{print $3}}'"
            )
            memory_utilization = subprocess.check_output(memory_cmd, shell=True).decode('utf-8').strip()
            mem_gb = (int(memory_utilization[:-2]) / 1024.0) if memory_utilization.endswith('Mi') and memory_utilization[:-2].isdigit() else 0.0

            pods.append({
                'namespace': namespace,
                'name': pod_name,
                'node_name': node_name,
                'cpu_utilization': f"{cpu_utilization:.2f}",
                'memory_utilization_gb': f"{mem_gb:.2f} GB",
            })

        except ValueError as e:
            print(f"Error processing pod row '{pod}': {e}")
            continue

    return pods, namespace_counts, group_counts, group_order

def get_deploy_replica_data(cluster_name, aws_session):
    """
    Returns:
      deployments_info: flat list of {namespace, deployment, desired, ready}
      deployments_by_ns: {namespace: [ ... rows ... ]}
    """
    deployments_info = []
    deployments_by_ns = {}

    ctx = _kubectl_ctx(aws_session, cluster_name)
    cmd = (
        f"kubectl get deploy -A --context={ctx} "
        "-o jsonpath='{range .items[*]}{.metadata.namespace}|{.metadata.name}|{.spec.replicas}|{.status.readyReplicas} {end}'"
    )
    try:
        items = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split()
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl for deployments: {e}")
        return deployments_info, deployments_by_ns

    for item in items:
        parts = item.split('|')
        if len(parts) != 4:
            continue
        ns, name, desired, ready = parts
        # Normalize ints / handle None
        try:
            desired_i = int(desired) if desired and desired.isdigit() else 0
        except Exception:
            desired_i = 0
        try:
            ready_i = int(ready) if ready and ready.isdigit() else 0
        except Exception:
            ready_i = 0

        row = {
            'namespace': ns,
            'deployment': name,
            'desired': desired_i,
            'ready': ready_i
        }
        deployments_info.append(row)
        deployments_by_ns.setdefault(ns, []).append(row)

    return deployments_info, deployments_by_ns

def generate_html_report(clusters_info, current_env):
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
            body { font-family: Arial, sans-serif; margin: 20px; background-color: white; color: black; transition: all 0.3s ease; }
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
            .dropdown { margin-bottom: 10px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
            .env-selector { margin-bottom: 20px; text-align: center; font-weight: bold; color: black; }
            #env-select { border: 2px solid black; font-weight: bold; padding: 5px; }
            .footer { text-align: center; margin-top: 50px; font-size: 14px; font-weight: bold; }
            .footer span { color: red; }
            .timestamp { text-align: right; font-size: 14px; color: grey; font-weight: bold; margin-bottom: 20px; }
            .muted { color: #555; font-weight: normal; font-size: 14px; }
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

        {% for cluster in clusters %}
        <div id="cluster-{{ cluster.account }}" style="display: {% if cluster.account == current_env %}block{% else %}none{% endif %};">
        <h2>{{ cluster.name }} ({{ cluster.account }} - {{ cluster.region }})</h2>

        <h3>Pods Count by Namespace Suffix</h3>
        <table>
            <thead>
                <tr>
                    <th>Group</th>
                    <th>Pod Count</th>
                </tr>
            </thead>
            <tbody>
            {% for group in cluster.group_order %}
                <tr>
                    <td>{{ group }}</td>
                    <td>{{ cluster.group_counts.get(group, 0) }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

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
            <div>
                <label for="suffix-select-{{ cluster.name }}">Filter by Namespace Suffix:</label>
                <select id="suffix-select-{{ cluster.name }}" onchange="filterBySuffix(this.value, '{{ cluster.name }}')">
                    <option value="">All</option>
                    {% for sfx in cluster.group_order %}
                        {% if sfx != 'others' %}
                        <option value="{{ sfx }}">{{ sfx }}</option>
                        {% endif %}
                    {% endfor %}
                </select>
                <span class="muted">(applies to Pods & Deployments below)</span>
            </div>
            <div>
                <label for="namespace-select-{{ cluster.name }}">Select Namespace:</label>
                <select id="namespace-select-{{ cluster.name }}" onchange="filterPodsAndDeploys(this.value, '{{ cluster.name }}')">
                    <option value="">Show All</option>
                    {% for ns in cluster.namespace_counts.keys() | sort %}
                    <option value="{{ ns }}">{{ ns }} ({{ cluster.namespace_counts[ns] }} Pods)</option>
                    {% endfor %}
                </select>
            </div>
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
                    <td class="ns">{{ pod.namespace }}</td>
                    <td>{{ pod.name }}</td>
                    <td>{{ pod.node_name }}</td>
                    <td>{{ pod.cpu_utilization }}</td>
                    <td>{{ pod.memory_utilization_gb }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        <h3>Replica Count by Deployment (per Namespace)</h3>
        <div class="dropdown">
            <div>
                <label for="replica-namespace-select-{{ cluster.name }}">Select Namespace:</label>
                <select id="replica-namespace-select-{{ cluster.name }}" onchange="filterDeployments(this.value, '{{ cluster.name }}')">
                    <option value="">Show All</option>
                    {% for ns in cluster.deployments_by_ns.keys() | sort %}
                    <option value="{{ ns }}">{{ ns }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <table id="replica-table-{{ cluster.name }}">
            <thead>
                <tr>
                    <th>Namespace</th>
                    <th>Application (Deployment)</th>
                    <th>Desired Replicas</th>
                    <th>Ready Replicas</th>
                </tr>
            </thead>
            <tbody>
            {% for d in cluster.deployments_info %}
                <tr class="deploy-row" data-namespace="{{ d.namespace }}">
                    <td class="ns">{{ d.namespace }}</td>
                    <td>{{ d.deployment }}</td>
                    <td>{{ d.desired }}</td>
                    <td>{{ d.ready }}</td>
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
            {% set max_cpu_pods = cluster.pods_info | sort(attribute='cpu_utilization', reverse=True)[:5] %}
            {% set max_memory_pods = cluster.pods_info | sort(attribute='memory_utilization_gb', reverse=True)[:5] %}
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
        </div>
        {% endfor %}

        <a href="eks_report.html" download="eks_report.html" class="download-link">Download Report</a>

        <div class="footer">
            Build with <span>❤️</span> VENERABLE
        </div>

        <script>
            function changeEnvironment() {
                const envSelect = document.getElementById('env-select');
                const selectedEnv = envSelect.value;
                {% for account in accounts %}
                document.getElementById('cluster-{{ account.name }}').style.display = 'none';
                {% endfor %}
                document.getElementById('cluster-' + selectedEnv).style.display = 'block';
            }

            function filterRowsByNamespace(rows, namespace) {
                for (let i = 0; i < rows.length; i++) {
                    const rowNs = rows[i].getAttribute('data-namespace');
                    rows[i].style.display = (namespace === '' || namespace === rowNs) ? '' : 'none';
                }
            }

            function filterPodsAndDeploys(namespace, clusterName) {
                // Filter Pods
                const podTable = document.getElementById('pod-table-' + clusterName);
                const podRows = podTable.getElementsByClassName('pod-row');
                filterRowsByNamespace(podRows, namespace);

                // Filter Deployments
                const depTable = document.getElementById('replica-table-' + clusterName);
                const depRows = depTable.getElementsByClassName('deploy-row');
                filterRowsByNamespace(depRows, namespace);
            }

            function filterDeployments(namespace, clusterName) {
                const depTable = document.getElementById('replica-table-' + clusterName);
                const depRows = depTable.getElementsByClassName('deploy-row');
                filterRowsByNamespace(depRows, namespace);
            }

            function filterBySuffix(suffix, clusterName) {
                // Applies to both Pods & Deployments (by namespace ending)
                const podTable = document.getElementById('pod-table-' + clusterName);
                const podRows = podTable.getElementsByClassName('pod-row');
                const depTable = document.getElementById('replica-table-' + clusterName);
                const depRows = depTable.getElementsByClassName('deploy-row');

                const showBySuffix = (row) => {
                    const nsCell = row.querySelector('.ns');
                    if (!nsCell) return true;
                    const ns = nsCell.textContent || '';
                    if (!suffix) return true; // "All"
                    return ns.endsWith(suffix);
                };

                for (let i = 0; i < podRows.length; i++) {
                    podRows[i].style.display = showBySuffix(podRows[i]) ? '' : 'none';
                }
                for (let i = 0; i < depRows.length; i++) {
                    depRows[i].style.display = showBySuffix(depRows[i]) ? '' : 'none';
                }

                // Clear specific-namespace filters when suffix changes
                const nsSelPods = document.getElementById('namespace-select-' + clusterName);
                if (nsSelPods) nsSelPods.value = '';
                const nsSelDeploys = document.getElementById('replica-namespace-select-' + clusterName);
                if (nsSelDeploys) nsSelDeploys.value = '';
            }

            function filterMaxUtilization(metric, clusterName) {
                var maxCpuRows = document.querySelectorAll('#max-utilization-table-' + clusterName + ' .max-cpu-row');
                var maxMemoryRows = document.querySelectorAll('#max-utilization-table-' + clusterName + ' .max-memory-row');

                if (metric === 'cpu') {
                    for (let i = 0; i < maxCpuRows.length; i++) maxCpuRows[i].style.display = '';
                    for (let i = 0; i < maxMemoryRows.length; i++) maxMemoryRows[i].style.display = 'none';
                } else if (metric === 'memory') {
                    for (let i = 0; i < maxCpuRows.length; i++) maxCpuRows[i].style.display = 'none';
                    for (let i = 0; i < maxMemoryRows.length; i++) maxMemoryRows[i].style.display = '';
                }
            }
        </script>
    </body>
    </html>
    """

    total_clusters = len(clusters_info)
    total_nodes = sum(len(cluster['nodes']) for cluster in clusters_info)
    total_pods = sum(len(cluster['pods_info']) for cluster in clusters_info)

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
    environment = event.get('queryStringParameters', {}).get('environment', 'dev')

    clusters_info = []
    for account in accounts:
        set_aws_credentials(account['name'])
        session = get_aws_session(account['region'])
        clusters = get_clusters(session)

        for cluster in clusters:
            nodes = get_nodes_and_metrics(cluster, session)
            pods_info, namespace_counts, group_counts, group_order = get_pods_and_metrics(cluster, session, account['name'])
            deployments_info, deployments_by_ns = get_deploy_replica_data(cluster, session)

            clusters_info.append({
                'name': cluster,
                'account': account['name'],
                'region': account['region'],
                'nodes': nodes,
                'pods_info': pods_info,
                'pods': {pod['namespace']: 1 for pod in pods_info},  # kept same as your code
                'namespace_counts': namespace_counts,
                'group_counts': group_counts,
                'group_order': group_order,
                'deployments_info': deployments_info,
                'deployments_by_ns': deployments_by_ns
            })

    html_content = generate_html_report(clusters_info, environment)
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': html_content
    }

if __name__ == '__main__':
    # Simulate a request for local testing
    event = {'queryStringParameters': {'environment': 'dev'}}
    result = lambda_handler(event, None)
    with open('eks_dashboard.html', 'w') as f:
        f.write(result['body'])
    print("Dashboard HTML generated.")
