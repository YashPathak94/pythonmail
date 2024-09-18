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

            /* Highlight colors for different environments */
            .highlight-dev { background-color: #36f4ce; }
            .highlight-idev { background-color: #36f4ce; }
            .highlight-intg { background-color: #36f4ce; }
            .highlight-prod { background-color: #36f4ce; }
            .highlight-accp { background-color: #36f4ce; }
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

        <!-- Cluster Summary Table -->
        <h3>Cluster Summary (Total Nodes & Pods per Cluster)</h3>
        <table id="cluster-summary-table">
            <thead>
                <tr>
                    <th>Total Clusters</th>
                    <th>Total Nodes</th>
                    <th>Total Pods</th>
                </tr>
            </thead>
            <tbody>
                {% for cluster in clusters %}
                <tr id="summary-{{ cluster.account }}" class="summary-row">
                    <td>{{ cluster.name }}</td>
                    <td>{{ cluster.nodes | length }}</td>
                    <td>{{ cluster.pods_info | length }}</td>
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
                    <th>CPU Capacity (vCPU)</th>
                    <th>Memory Capacity (GB)</th>
                    <th>CPU Utilization (%)</th>
                    <th>Memory Utilization (GB)</th>
                    <th>Memory Utilization (%)</th>
                </tr>
            </thead>
            <tbody>
            {% for node in cluster.nodes %}
                <tr class="node-row">
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

                // Remove previous highlights from Cluster Summary rows
                {% for account in accounts %}
                document.getElementById('summary-{{ account.name }}').classList.remove('highlight-dev', 'highlight-idev', 'highlight-intg', 'highlight-prod', 'highlight-accp');
                {% endfor %}

                // Add the highlight class for the selected environment in Cluster Summary only
                if (selectedEnv === 'dev') {
                    document.getElementById('summary-' + selectedEnv).classList.add('highlight-dev');
                } else if (selectedEnv === 'idev') {
                    document.getElementById('summary-' + selectedEnv).classList.add('highlight-idev');
                } else if (selectedEnv === 'intg') {
                    document.get.getElementById('summary-' + selectedEnv).classList.add('highlight-intg');
                }
                } else if (selectedEnv === 'prod') {
                    document.get.getElementById('summary-' + selectedEnv).classList.add('highlight-prod');
                }
                } else if (selectedEnv === 'accp') {
                    document.get.getElementById('summary-' + selectedEnv).classList.add('highlight-accp');
                }

                // Hide all clusters' nodes information
                {% for account in accounts %}
                document.getElementById('cluster-{{ account.name }}').style.display = 'none';
                {% endfor %}
                
                // Show the nodes information for the selected environment
                document.getElementById('cluster-' + selectedEnv).style.display = 'block';
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
        current_env=current_env,
        timestamp=timestamp
    )

    return html_content

