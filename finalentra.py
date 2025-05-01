from datetime import datetime, timezone

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
 
