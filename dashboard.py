import boto3
import subprocess
from flask import Flask, render_template_string, request

app = Flask(__name__)

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
    nodes = int(subprocess.check_output(cmd, shell=True).decode('utf-8').strip())
    
    cmd = f"kubectl get pods --all-namespaces --context=arn:aws:eks:{aws_session.region_name}:{aws_session.client('sts').get_caller_identity()['Account']}:cluster/{cluster_name} --no-headers | wc -l"
    pods = int(subprocess.check_output(cmd, shell=True).decode('utf-8').strip())
    
    return nodes, pods

@app.route('/')
def index():
    total_clusters = 0
    total_nodes = 0
    total_pods = 0
    cluster_data = []

    for account in accounts:
        session = get_aws_session(account)
        clusters = get_clusters(session)
        total_clusters += len(clusters)

        for cluster in clusters:
            nodes, pods = get_nodes_and_pods(cluster, session)
            total_nodes += nodes
            total_pods += pods
            cluster_data.append({
                'account': account['name'],
                'region': account['region'],
                'name': cluster,
                'nodes': nodes,
                'pods': pods
            })

    html = """
    <html>
    <head>
        <title>EKS Cluster Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; }
            table { width: 100%; border-collapse: collapse; }
            table, th, td { border: 1px solid black; }
            th, td { padding: 10px; text-align: left; }
        </style>
    </head>
    <body>
        <h1>EKS Cluster Dashboard</h1>
        <p>Total EKS Clusters: {{ total_clusters }}</p>
        <p>Total Nodes across all clusters: {{ total_nodes }}</p>
        <p>Total Pods across all clusters: {{ total_pods }}</p>

        <form action="/cluster" method="post">
            <label for="cluster">Select a cluster:</label>
            <select name="cluster" id="cluster">
                {% for cluster in cluster_data %}
                <option value="{{ cluster.name }}|{{ cluster.account }}|{{ cluster.region }}">{{ cluster.name }} ({{ cluster.account }}, {{ cluster.region }})</option>
                {% endfor %}
            </select>
            <input type="submit" value="View Details">
        </form>
    </body>
    </html>
    """

    return render_template_string(html, total_clusters=total_clusters, total_nodes=total_nodes, total_pods=total_pods, cluster_data=cluster_data)

@app.route('/cluster', methods=['POST'])
def cluster_details():
    selected_cluster = request.form['cluster']
    cluster_name, account_name, region_name = selected_cluster.split('|')

    for account in accounts:
        if account['name'] == account_name and account['region'] == region_name:
            session = get_aws_session(account)
            nodes, pods = get_nodes_and_pods(cluster_name, session)
            break

    html = f"""
    <html>
    <head>
        <title>EKS Cluster Details</title>
        <style>
            body { font-family: Arial, sans-serif; }
            table { width: 100%; border-collapse: collapse; }
            table, th, td { border: 1px solid black; }
            th, td { padding: 10px; text-align: left; }
        </style>
    </head>
    <body>
        <h1>Cluster: {cluster_name} ({account_name}, {region_name})</h1>
        <p>Number of Nodes: {nodes}</p>
        <p>Number of Pods: {pods}</p>
        <a href="/">Back to Dashboard</a>
    </body>
    </html>
    """

    return html

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
