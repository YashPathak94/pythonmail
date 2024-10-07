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
        'environment': 'dr'  # 'dr' uses its own environment name
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
    if account['name'] == 'dr':
        # Prompt user for AWS credentials
        print(f"Please enter AWS credentials for the '{account['name']}' cluster:")
        aws_access_key_id = input('AWS_ACCESS_KEY_ID: ').strip()
        aws_secret_access_key = input('AWS_SECRET_ACCESS_KEY: ').strip()
        aws_session_token = input('AWS_SESSION_TOKEN (leave blank if not applicable): ').strip()

        os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
        os.environ['AWS_SESSION_TOKEN'] = aws_session_token  # May be empty

        if not aws_access_key_id or not aws_secret_access_key:
            print(f"Warning: AWS credentials for '{account['name']}' are not set correctly.")
            return False

        print(f"Using credentials for environment: '{account['name']}'")
        return True
    else:
        # Use environment variables
        environment = account['environment']
        os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
        os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
        os.environ['AWS_SESSION_TOKEN'] = os.getenv(f'{environment}_AWS_SESSION_TOKEN', '')

        if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
            print(f"Warning: AWS credentials for '{account['name']}' are not set correctly.")
            return False

        print(f"Using credentials for environment: '{account['name']}'")
        return True

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

def update_kubeconfig(cluster_name, region, account_name):
    try:
        env = os.environ.copy()
        if account_name == 'dr':
            # Prompt user for the 'aws eks update-kubeconfig' command
            print(f"Please enter the 'aws eks update-kubeconfig' command for the '{cluster_name}' cluster.")
            print("For example: eks update-kubeconfig --name my-cluster --region us-west-2 --role-arn arn:aws:iam::123456789012:role/YourRole")
            kubeconfig_command = input('Command (without "aws " prefix): ').strip()
            if not kubeconfig_command.startswith('eks update-kubeconfig'):
                print("Invalid command. It should start with 'eks update-kubeconfig'.")
                return False
            # Prepend 'aws ' to the command
            cmd = f"aws {kubeconfig_command}"
        else:
            cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region} --alias {cluster_name}"
        subprocess.check_output(cmd, shell=True, env=env)
        print(f"Kubeconfig updated for cluster '{cluster_name}'")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error updating kubeconfig for cluster '{cluster_name}': {e.output.decode()}")
        return False

# Rest of your functions (e.g., get_nodes_and_metrics, get_pods_and_metrics) remain the same...

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
            if not update_kubeconfig(cluster, account['region'], account['name']):
                continue

            # Proceed with the rest of your code
            # For example:
            # nodes = get_nodes_and_metrics(cluster)
            # pods_info, namespace_counts, group_counts, group_order = get_pods_and_metrics(cluster, account['name'])
            # clusters_info.append({
            #     'name': cluster,
            #     'account': account['name'],
            #     'region': account['region'],
            #     'nodes': nodes,
            #     'pods_info': pods_info,
            #     'namespace_counts': namespace_counts,
            #     'group_counts': group_counts,
            #     'group_order': group_order
            # })

    # Generate the HTML report
    # html_content = generate_html_report(clusters_info, environment)
    # For the purpose of this example, we'll just print a message
    print("Script execution completed.")

if __name__ == '__main__':
    # Simulate a request for local testing
    event = {
        'queryStringParameters': {
            'environment': 'dev'
        }
    }
    lambda_handler(event, None)
