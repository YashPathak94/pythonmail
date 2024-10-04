
def set_aws_credentials(environment):
    """
    Dynamically set AWS credentials in the environment for the given environment.
    For 'dr', use the same credentials as 'prod'.
    """
    if environment == 'dr':
        environment = 'prod'  # Use 'prod' credentials for 'dr'

    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
    
    # Only set AWS_SESSION_TOKEN if it's not None
    session_token = os.getenv(f'{environment}_AWS_SESSION_TOKEN')
    if session_token:
        os.environ['AWS_SESSION_TOKEN'] = session_token

    # Check for missing credentials
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        print(f"Error: AWS credentials for {environment} are not set correctly.")
        sys.exit(1)

    print(f"Using credentials for environment: {environment}")




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
        'region': 'us-east-1',
        'environment': 'dev'
    },
    {
        'name': 'idev',
        'region': 'us-east-1',
        'environment': 'idev'
    },
    {
        'name': 'intg',
        'region': 'us-east-1',
        'environment': 'intg'
    },
    {
        'name': 'prod',
        'region': 'us-east-1',
        'environment': 'prod'
    },
    {
        'name': 'dr',
        'region': 'us-west-2',
        'environment': 'dr',
        'credentials': {
            'AWS_ACCESS_KEY_ID': 'YOUR_DR_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY': 'YOUR_DR_SECRET_ACCESS_KEY',
            # 'AWS_SESSION_TOKEN': 'YOUR_DR_SESSION_TOKEN'  # Uncomment if needed
        }
    },
    # Add more accounts as needed
]

# Define suffixes for each environment
suffixes_map = {
    'dev': ['dev', 'devb', 'devc'],
    'intg': ['intg', 'intgb', 'intgc'],
    'prod': ['proda', 'prodb'],
    'accp': ['accp', 'accpb', 'accpc'],
    'idev': [],
    'dr': []  # 'dr' suffix same as 'idev' cluster
}

def set_aws_credentials(account):
    """
    Dynamically set AWS credentials in the environment for the given account.
    """
    if 'credentials' in account:
        # Use credentials provided in the account dictionary
        os.environ['AWS_ACCESS_KEY_ID'] = account['credentials'].get('AWS_ACCESS_KEY_ID')
        os.environ['AWS_SECRET_ACCESS_KEY'] = account['credentials'].get('AWS_SECRET_ACCESS_KEY')
        os.environ['AWS_SESSION_TOKEN'] = account['credentials'].get('AWS_SESSION_TOKEN', '')
    else:
        # Use environment variables
        environment = account['environment']
        os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
        os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
        os.environ['AWS_SESSION_TOKEN'] = os.getenv(f'{environment}_AWS_SESSION_TOKEN', '')

    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        print(f"Warning: AWS credentials for {account['name']} are not set correctly.")
        return False

    print(f"Using credentials for environment: {account['name']}")
    return True

def get_aws_session(region):
    return boto3.Session(region_name=region)

# (Assuming the rest of your functions remain the same)
# Make sure to use the updated set_aws_credentials function

def lambda_handler(event, context):
    # Default to 'dev' environment if not specified
    environment = event.get('queryStringParameters', {}).get('environment', 'dev')

    clusters_info = []

    for account in accounts:
        if not set_aws_credentials(account):
            continue

        session = get_aws_session(account['region'])
        clusters = get_clusters(session)

        for cluster in clusters:
            # Update kubeconfig for the cluster
            if not update_kubeconfig(cluster, session):
                continue

            nodes = get_nodes_and_metrics(cluster, session)
            pods_info, namespace_counts, group_counts, group_order = get_pods_and_metrics(cluster, session, account['name'])

            clusters_info.append({
                'name': cluster,
                'account': account['name'],
                'region': account['region'],
                'nodes': nodes,
                'pods_info': pods_info,
                'pods': {pod['namespace']: 1 for pod in pods_info},
                'namespace_counts': namespace_counts,
                'group_counts': group_counts,
                'group_order': group_order
            })

    # Generate the HTML report
    html_content = generate_html_report(clusters_info, environment)

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
            'environment': 'dev'
        }
    }
    result = lambda_handler(event, None)
    with open('eks_dashboard.html', 'w') as f:
        f.write(result['body'])
    print("Dashboard HTML generated.")

