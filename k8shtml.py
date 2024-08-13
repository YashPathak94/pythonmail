import boto3
from jinja2 import Template
import os

# Define AWS credentials and regions for different accounts
accounts = [
    {
        'name': 'Account 1',
        'access_key': 'your-access-key-1',
        'secret_key': 'your-secret-key-1',
        'region': 'us-west-1'
    },
    {
        'name': 'Account 2',
        'access_key': 'your-access-key-2',
        'secret_key': 'your-secret-key-2',
        'region': 'us-east-1'
    },
    # Add more accounts as needed
]

def get_aws_session(account):
    return boto3.Session(
        aws_access_key_id=account['access_key'],
        aws_secret_access_key=account['secret_key'],
        region_name=account['region']
    )

def get_clusters(aws_session):
    eks_client = aws_session.client('eks')
    clusters = eks_client.list_clusters()['clusters']
    return clusters

def get_nodes_and_pods(cluster_name, aws_session):
    cmd = f"kubectl get nodes --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | wc -l"
    nodes = int(os.popen(cmd).read().strip())
    
    cmd = f"kubectl get pods --all-namespaces --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | wc -l"
    pods = int(os.popen(cmd).read().strip())
    
    return nodes, pods

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
            th { background-color: #f2f2f2; }
            h2 { margin-top: 50px; }
            .download-link { margin-top: 20px; }
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
            <tr>
                <th>Metric</th>
                <th>Count</th>
            </tr>
            <tr>
                <td>Nodes</td>
                <td>{{ cluster.nodes }}</td>
            </tr>
            <tr>
                <td>Pods</td>
                <td>{{ cluster.pods }}</td>
            </tr>
        </table>
        {% endfor %}
        <a href="eks_report.html" download="eks_report.html" class="download-link">Download Report</a>
    </body>
    </html>
    """
    total_clusters = len(clusters_info)
    total_nodes = sum(cluster['nodes'] for cluster in clusters_info)
    total_pods = sum(cluster['pods'] for cluster in clusters_info)
    
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
            nodes, pods = get_nodes_and_pods(cluster, session)
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
