import os
import sys
import boto3
import subprocess
from jinja2 import Template
from datetime import datetime
from datetime import datetime, timezone

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
    access_key = os.getenv(f'{environment.upper()}_AWS_ACCESS_KEY_ID')
    secret_key = os.getenv(f'{environment.upper()}_AWS_SECRET_ACCESS_KEY')
    session_token = os.getenv(f'{environment.upper()}_AWS_SESSION_TOKEN')  # Optional

    if not access_key or not secret_key:
        print(f"Error: AWS credentials for {environment} are not set correctly.")
        sys.exit(1)

    os.environ['AWS_ACCESS_KEY_ID'] = access_key
    os.environ['AWS_SECRET_ACCESS_KEY'] = secret_key
    if session_token:
        os.environ['AWS_SESSION_TOKEN'] = session_token

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

def generate_html_report(clusters_info, current_env):
    # Generate a timestamp with the timezone (UTC in this case)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")

    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EKS Cluster Dashboard</title>
        <link rel="icon" type="image/x-icon" href="favicon.ico">
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: white;
                color: black;
                transition: all 0.3s ease;
            }

            .custom-container {
                padding: 0 5px;
            }

            .bg-dark {
                background-color: #231161 !important;
            }

            .px-2 {
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }

            .heading {
                color: #0396A8;
            }

            .table-wrap {
                white-space: normal;
                word-break: break-word;
            }

            .navbar {
                padding: 8px;
            }

            .center {
                border: 2px solid;
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                padding: 10px;
            }

            .boarder-container {
                border: 2px solid black;
            }

            .card:hover {
                box-shadow: 2px 3px 7px -3px;
            }

            label {
                font-weight: bold;
            }

            .ven-logo {
                width: 15px;
            }

            @media (max-width: 576px) {
                .ven-logo {
                    display: block;
                }

                .navbar-nav .nav-link {
                    font-size: 16px;
                }
            }

            .navbar-expand-lg .navbar-nav {
                display: flex;
                flex-wrap: nowrap;
                overflow-x: auto;
            }

            .navbar-nav .nav-link {
                white-space: nowrap;
                padding-left: 10px;
                padding-right: 10px;
            }

            .footer {
                text-align: center;
                margin-top: 50px;
                font-size: 14px;
                font-weight: bold;
            }

            .footer span {
                color: red;
            }

            .gauge-container {
                width: 100px;
                height: 50px;
                background: #e6e6e6;
                border-radius: 5px;
                position: relative;
            }

            .gauge-fill {
                height: 100%;
                border-radius: 5px;
            }

            .gauge-label {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-weight: bold;
            }
        </style>
    </head>
    <body class="bg-dark text-white">
        <!-- Navbar -->
        <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
            <a class="navbar-brand" href="https://www.venerable.com/">
                <img src="/basdashboard/images/venerable_logo.png" class="ven-logo" alt="venerable.com">
            </a>
            <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav">
                    <li class="nav-item active">
                        <a class="nav-link" href="#">Home</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#">Dashboard</a>
                    </li>
                </ul>
            </div>
        </nav>

        <!-- Main Content -->
        <div class="container mt-4 custom-container">
            <h1 class="heading text-center">EKS Dashboard</h1>

            <!-- Gauge Example -->
            <div class="gauge-container mt-4 center">
                <div class="gauge-fill" style="width: 50%; background-color: green;"></div>
                <div class="gauge-label">50%</div>
            </div>

            <h2 class="heading">Cluster Summary</h2>
            <table class="table table-bordered table-wrap text-white">
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
            <div class="cluster-section" id="cluster-{{ cluster.account }}" style="display: {% if cluster.account == current_env %}block{% else %}none{% endif %};">
            <h2>{{ cluster.name }} ({{ cluster.account }} - {{ cluster.region }})</h2>

            <h3>Pods Count by Namespace Suffix</h3>
            <table class="table table-bordered table-wrap text-white">
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
            <table class="table table-bordered table-wrap text-white">
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
                    {% for namespace in cluster.namespace_counts %}
                    <option value="{{ namespace }}">{{ namespace }} ({{ cluster.namespace_counts[namespace] }} Pods)</option>
                    {% endfor %}
                </select>
            </div>
            <table id="pod-table-{{ cluster.name }}" class="table table-bordered table-wrap text-white">
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
            <table id="max-utilization-table-{{ cluster.name }}" class="table table-bordered table-wrap text-white">
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

            <a href="eks_report.html" download="eks_report.html" class="download-link text-white">Download Report</a>
        </div>

        <div class="footer">
            Build with <span>❤️</span> VENERABLE
        </div>

        <script src="https://code.jquery.com/jquery-3.2.1.slim.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.12.9/umd/popper.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js"></script>
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
        timestamp=timestamp  # Pass the timestamp with timezone to the template
    )

    return html_content

def lambda_handler(event, context):
    # Default to 'dev' environment and first suffix if not specified
    query_params = event.get('queryStringParameters') or {}
    environment = query_params.get('environment', 'dev').lower()
    suffix = query_params.get('suffix')

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

from flask import Flask, session, redirect, url_for, request, render_template, send_from_directory
import msal
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'replace-with-a-secure-random-value')

# Azure AD / Entra OIDC settings
CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
TENANT_ID = os.environ.get('AZURE_TENANT_ID')
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = '/getAToken'  # must match the redirect URI set in Entra
SCOPE = ["openid", "profile", "email"]
SESSION_TYPE = 'filesystem'  # token cache stored server-side

@app.route('/')
def index():
    # If user not logged in, redirect to login
    if not session.get('user'):
        return redirect(url_for('login'))
    # Serve your static dashboard
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/login')
def login():
    # Create MSAL confidential client
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    # Build the auth request URL
    auth_url = msal_app.get_authorization_request_url(
        scopes=SCOPE,
        redirect_uri=url_for('authorized', _external=True)
    )
    return redirect(auth_url)

@app.route(REDIRECT_PATH)
def authorized():
    # Handle the response from Azure
    code = request.args.get('code')
    if not code:
        return "Authorization failed.", 400

    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    # Exchange code for token
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=url_for('authorized', _external=True)
    )
    if 'access_token' in result:
        # Store user info in session
        session['user'] = {
            'name': result.get('id_token_claims').get('name'),
            'email': result.get('id_token_claims').get('email')
        }
        return redirect(url_for('index'))
    else:
        return "Could not acquire token: " + str(result.get('error_description')), 400

@app.route('/logout')
def logout():
    # Clear session and redirect to Azure logout
    session.clear()
    logout_url = f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri={url_for('index', _external=True)}"
    return redirect(logout_url)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)  # serve on HTTP port 80 inside EC2 container/instance
 
