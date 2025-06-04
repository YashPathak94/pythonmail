
import boto3
from datetime import datetime
from botocore.exceptions import ClientError

# Configuration for multiple AWS accounts using credentials
accounts = {
    "dev": {
        "aws_access_key_id": "REPLACE_WITH_DEV_ACCESS_KEY",
        "aws_secret_access_key": "REPLACE_WITH_DEV_SECRET_KEY",
        "aws_session_token": "REPLACE_WITH_DEV_SESSION_TOKEN",
        "region": "us-east-1",
        "domain_filter": "*.dev.vapps.net",
        "secret_prefix": "bas-chain"
    },
    "intg": {
        "aws_access_key_id": "REPLACE_WITH_INTG_ACCESS_KEY",
        "aws_secret_access_key": "REPLACE_WITH_INTG_SECRET_KEY",
        "aws_session_token": "REPLACE_WITH_INTG_SESSION_TOKEN",
        "region": "us-east-1",
        "domain_filter": "*.intg.vapps.net",
        "secret_prefix": "bas-chain"
    },
    "accp": {
        "aws_access_key_id": "REPLACE_WITH_ACCP_ACCESS_KEY",
        "aws_secret_access_key": "REPLACE_WITH_ACCP_SECRET_KEY",
        "aws_session_token": "REPLACE_WITH_ACCP_SESSION_TOKEN",
        "region": "us-east-1",
        "domain_filter": "*.accp.vapps.net",
        "secret_prefix": "bas-chain"
    },
    "prod": {
        "aws_access_key_id": "REPLACE_WITH_PROD_ACCESS_KEY",
        "aws_secret_access_key": "REPLACE_WITH_PROD_SECRET_KEY",
        "aws_session_token": "REPLACE_WITH_PROD_SESSION_TOKEN",
        "region": "us-east-1",
        "domain_filter": "*.prod.vapps.net",
        "secret_prefix": "bas-chain"
    }
}

def format_date(dt):
    return dt.strftime('%Y-%m-%d') if dt else "-"

def fetch_acm_data(session, region, domain_filter):
    acm_client = session.client('acm', region_name=region)
    certificates_data = []

    paginator = acm_client.get_paginator('list_certificates')
    for page in paginator.paginate(CertificateStatuses=['ISSUED']):
        for cert_summary in page['CertificateSummaryList']:
            cert_arn = cert_summary['CertificateArn']
            try:
                cert_details = acm_client.describe_certificate(CertificateArn=cert_arn)['Certificate']
                domain_name = cert_details.get('DomainName')
                if domain_filter.replace("*", "") not in domain_name:
                    continue

                cert_data = {
                    'DomainName': domain_name,
                    'Status': cert_details.get('Status'),
                    'Type': cert_details.get('Type'),
                    'RequestedAt': format_date(cert_details.get('CreatedAt')),
                    'ImportedAt': format_date(cert_details.get('ImportedAt')),
                    'IssuedAt': format_date(cert_details.get('IssuedAt')),
                    'NotAfter': format_date(cert_details.get('NotAfter')),
                    'RenewalEligibility': cert_details.get('RenewalEligibility', "-"),
                    'InUseBy': cert_details.get('InUseBy', [])
                }
                certificates_data.append(cert_data)
            except ClientError:
                continue
    return certificates_data

def fetch_secrets_data(session, region, secret_prefix):
    secrets_client = session.client('secretsmanager', region_name=region)
    secrets_data = []

    paginator = secrets_client.get_paginator('list_secrets')
    for page in paginator.paginate():
        for secret in page['SecretList']:
            if not secret['Name'].startswith(secret_prefix):
                continue
            try:
                details = secrets_client.describe_secret(SecretId=secret['ARN'])
                secret_data = {
                    'Name': details['Name'],
                    'RotationEnabled': "Yes" if details.get('RotationEnabled') else "No",
                    'Versions': f"{len(details.get('VersionIdsToStages', {}))} versions",
                    'ReplicationRegions': ", ".join([r['Region'] for r in details.get('ReplicationStatus', [])]) or "-"
                }
                secrets_data.append(secret_data)
            except ClientError:
                continue
    return secrets_data

def generate_html_report(all_data):
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>ACM Certificates & Secrets Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h2 { background-color: #f57c00; color: white; padding: 10px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 30px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #333; color: white; }
        details summary { cursor: pointer; font-weight: bold; }
        .section { margin-bottom: 50px; }
    </style>
</head>
<body>
    <h1>Multi-Account Dashboard: ACM Certificates & Secrets</h1>
"""
    for account, data in all_data.items():
        html += f"""<div class="section">
    <h2>{account.upper()} Account - ACM Certificates for {accounts[account]['domain_filter']}</h2>
    <table>
        <tr>
            <th>Domain Name</th><th>Status</th><th>Type</th><th>Requested At</th><th>Imported At</th>
            <th>Issued At</th><th>Expires At</th><th>Renewal Eligibility</th><th>In Use By</th>
        </tr>"""
        for cert in data['certs']:
            html += f"""<tr>
            <td>{cert['DomainName']}</td><td>{cert['Status']}</td><td>{cert['Type']}</td>
            <td>{cert['RequestedAt']}</td><td>{cert['ImportedAt']}</td><td>{cert['IssuedAt']}</td>
            <td>{cert['NotAfter']}</td><td>{cert['RenewalEligibility']}</td>
            <td>
                <details>
                    <summary>{len(cert['InUseBy'])} resources</summary>
                    <ul>"""
            for item in cert['InUseBy']:
                html += f"<li>{item}</li>"
            html += "</ul></details></td></tr>"

        html += "</table><h2>Secrets: " + accounts[account]['secret_prefix'] + "*</h2><table>"
        html += "<tr><th>Name</th><th>Rotation Enabled</th><th>Versions</th><th>Replication Regions</th></tr>"
        for secret in data['secrets']:
            html += f"<tr><td>{secret['Name']}</td><td>{secret['RotationEnabled']}</td><td>{secret['Versions']}</td><td>{secret['ReplicationRegions']}</td></tr>"
        html += "</table></div>"
    html += "</body></html>"

    output_path = "acm_secrets_multi_account_dashboard.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Report saved to {output_path}")

# Main Execution
def main():
    all_account_data = {}
    for account, config in accounts.items():
        session = boto3.Session(
            aws_access_key_id=config['aws_access_key_id'],
            aws_secret_access_key=config['aws_secret_access_key'],
            aws_session_token=config['aws_session_token'],
            region_name=config['region']
        )
        certs = fetch_acm_data(session, config['region'], config['domain_filter'])
        secrets = fetch_secrets_data(session, config['region'], config['secret_prefix'])
        all_account_data[account] = {"certs": certs, "secrets": secrets}

    generate_html_report(all_account_data)

if __name__ == "__main__":
    main()
