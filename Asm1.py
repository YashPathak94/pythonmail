import boto3
from datetime import datetime

REGION = 'us-east-1'  # Change to your region
CERT_DOMAIN_FILTER = '*.dev.vapps.net'
SECRET_NAME_PREFIX = 'bas-chain'

def fetch_acm_certificates():
    acm = boto3.client('acm', region_name=REGION)
    paginator = acm.get_paginator('list_certificates')
    cert_details = []

    for page in paginator.paginate(CertificateStatuses=['ISSUED', 'PENDING_VALIDATION']):
        for cert_summary in page['CertificateSummaryList']:
            arn = cert_summary['CertificateArn']
            cert = acm.describe_certificate(CertificateArn=arn)['Certificate']

            domain = cert.get('DomainName', '')
            san_list = cert.get('SubjectAlternativeNames', [])
            if CERT_DOMAIN_FILTER not in domain and CERT_DOMAIN_FILTER not in str(san_list):
                continue  # Skip unrelated certs

            associated_resources = cert.get("InUseBy", [])
            cert_details.append({
                "DomainName": domain,
                "Status": cert.get('Status'),
                "Type": cert.get('Type'),
                "RequestedAt": cert.get('CreatedAt', ''),
                "ImportedAt": cert.get('ImportedAt', ''),
                "IssuedAt": cert.get('IssuedAt', ''),
                "NotAfter": cert.get('NotAfter', ''),
                "RenewalEligibility": cert.get('RenewalEligibility', 'N/A'),
                "InUseBy": associated_resources
            })

    return cert_details

def fetch_secrets_manager_details():
    sm = boto3.client('secretsmanager', region_name=REGION)
    secrets_data = []

    paginator = sm.get_paginator('list_secrets')
    for page in paginator.paginate():
        for secret in page['SecretList']:
            name = secret.get('Name')
            if not name.startswith(SECRET_NAME_PREFIX):
                continue

            description = secret.get('Description', '')
            rotation_enabled = secret.get('RotationEnabled', False)
            versions = sm.list_secret_version_ids(SecretId=name)
            version_count = len(versions.get('Versions', []))

            replication = secret.get('ReplicationStatus', [])
            regions = [r['Region'] for r in replication]

            secrets_data.append({
                "Name": name,
                "RotationEnabled": 'Yes' if rotation_enabled else 'No',
                "Versions": f"{version_count} versions",
                "ReplicationRegions": ', '.join(regions) if regions else 'None'
            })

    return secrets_data

def generate_acm_table(cert_data):
    table_html = """
    <h3>ACM Certificates for '*.dev.vapps.net'</h3>
    <table>
        <thead>
            <tr>
                <th>Domain Name</th>
                <th>Status</th>
                <th>Type</th>
                <th>Requested At</th>
                <th>Imported At</th>
                <th>Issued At</th>
                <th>Expires At</th>
                <th>Renewal Eligibility</th>
            </tr>
        </thead>
        <tbody>
    """
    for cert in cert_data:
        table_html += f"""
        <tr>
            <td>{cert['DomainName']}</td>
            <td>{cert['Status']}</td>
            <td>{cert['Type']}</td>
            <td>{cert['RequestedAt']}</td>
            <td>{cert['ImportedAt'] or '-'}</td>
            <td>{cert['IssuedAt'] or '-'}</td>
            <td>{cert['NotAfter']}</td>
            <td>{cert['RenewalEligibility']}</td>
        </tr>
        """

        # Nested table for "In Use By"
        if cert.get("InUseBy"):
            table_html += """
            <tr><td colspan="8">
                <b>In Use By:</b>
                <table style="margin-left:20px; background:#f9f9f9;">
                    <thead><tr><th>ARN</th></tr></thead>
                    <tbody>
            """
            for arn in cert["InUseBy"]:
                table_html += f"<tr><td>{arn}</td></tr>"
            table_html += "</tbody></table></td></tr>"

    table_html += "</tbody></table><br>"
    return table_html

def generate_secrets_table(secret_data):
    table_html = """
    <h3>Secrets: bas-chain*</h3>
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Rotation Enabled</th>
                <th>Versions</th>
                <th>Replication Regions</th>
            </tr>
        </thead>
        <tbody>
    """
    for secret in secret_data:
        table_html += f"""
        <tr>
            <td>{secret['Name']}</td>
            <td>{secret['RotationEnabled']}</td>
            <td>{secret['Versions']}</td>
            <td>{secret['ReplicationRegions']}</td>
        </tr>
        """
    table_html += "</tbody></table><br>"
    return table_html

def generate_dashboard_html(acm_data, secret_data):
    html = f"""
    <html>
    <head>
        <title>Dev Account Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            h2 {{ color: #333; }}
            h3 {{ color: #f57c00; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; font-size: 14px; }}
            th {{ background-color: #f57c00; color: white; }}
            table table {{ border: 1px solid #999; }}
            table table th {{ background-color: #ddd; color: #000; }}
            table table td {{ font-size: 13px; }}
        </style>
    </head>
    <body>
        <h2>Dev Account Dashboard: ACM Certificates & Secrets</h2>
        {generate_acm_table(acm_data)}
        {generate_secrets_table(secret_data)}
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    acm_data = fetch_acm_certificates()
    secret_data = fetch_secrets_manager_details()
    html_output = generate_dashboard_html(acm_data, secret_data)

    output_file = "asm_dashboard.html"
    with open(output_file, "w") as f:
        f.write(html_output)

    print(f"HTML dashboard written to: {output_file}")
