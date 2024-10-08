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
        'environment': 'dr'
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
    'dr': []
}

def set_aws_credentials(account):
    """
    Dynamically set AWS credentials in the environment for the given account.
    """
    environment = account['environment']
    aws_access_key_id = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv(f'{environment}_AWS_SESSION_TOKEN')

    if not aws_access_key_id or not aws_secret_access_key:
        print(f"Error: AWS credentials for '{account['name']}' are not set correctly.")
        return False

    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
    if aws_session_token:
        os.environ['AWS_SESSION_TOKEN'] = aws_session_token
    elif 'AWS_SESSION_TOKEN' in os.environ:
        del os.environ['AWS_SESSION_TOKEN']  # Remove if it was set previously

    print(f"Using credentials for environment: '{account['name']}'")
    return True

# Rest of your script remains the same
# ...

def main():
    environment = 'dev'

    clusters_info = []

    for account in accounts:
        if not set_aws_credentials(account):
            continue

        session = get_aws_session(account['region'])
        clusters = get_clusters(session)

        for cluster in clusters:
            # Update kubeconfig for the cluster
            context_name = update_kubeconfig(cluster, account['region'])
            if not context_name:
                continue  # Skip this cluster if unable to update kubeconfig

            # Add context to account
            account_copy = account.copy()  # Create a copy to avoid overwriting
            account_copy['context'] = context_name

            # Fetch nodes and pods
            nodes = get_nodes_and_metrics(account_copy)
            pods_info, namespace_counts, group_counts, group_order = get_pods_and_metrics(account_copy)

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

    # Output the report or save it to a file
    with open('eks_dashboard.html', 'w') as f:
        f.write(html_content)
    print("Dashboard HTML generated.")

if __name__ == '__main__':
    main()
