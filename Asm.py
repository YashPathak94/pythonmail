import boto3
from datetime import datetime, timezone
from jinja2 import Template

# ----------- CONFIGURATION -----------
REGION = 'us-east-1'
CERT_DOMAIN_FILTER = "*.dev.vapps.net"
SECRET_PREFIX_FILTER = "bas-chain"

# ----------- FETCH ACM CERTIFICATES -----------
def fetch_acm_certificates():
    acm = boto3.client('acm', region_name=REGION)
    paginator = acm.get_paginator('list_certificates')
    cert_details = []

    for page in paginator.paginate():
        for cert_summary in page['CertificateSummaryList']:
            arn = cert_summary['CertificateArn']
            cert = acm.describe_certificate(CertificateArn=arn)['Certificate']

            if CERT_DOMAIN_FILTER not in cert['DomainName']:
                continue

            associated_resources = cert.get("InUseBy", [])
            cert_details.append({
                "DomainName": cert.get('DomainName'),
                "Status": cert.get('Status'),
                "Type": cert.get('Type'),
                "IssuedAt": cert.get('IssuedAt', ''),
                "ImportedAt": cert.get('ImportedAt', ''),
                "NotAfter": cert.get('NotAfter', ''),
                "RequestedAt": cert.get('CreatedAt', ''),
                "RenewalEligibility": cert.get('RenewalEligibility', 'N/A'),
                "InUseBy": associated_resources
            })

    return cert_details

# ----------- FETCH SECRETS MANAGER DETAILS -----------
def fetch_secrets_details():
    secrets_client = boto3.client('secretsmanager', region_name=REGION)
    paginator = secrets_client.get_paginator('list_secrets')
    secrets_info = []

    for page in paginator.paginate():
        for secret in page['SecretList']:
            name = secret['Name']
            if not name.startswith(SECRET_PREFIX_FILTER):
                continue

            desc = secrets_client.describe_secret(SecretId=name)

            rotation_enabled = desc.get("RotationEnabled", False)
            versions = list(desc.get("VersionIdsToStages", {}).keys())
            replication_status = desc.get("ReplicationStatus", [])

            secrets_info.append({
                "Name": name,
                "RotationEnabled": rotation_enabled,
                "Versions": versions,
                "ReplicationStatus": replication_status
            })

    return secrets_info

# ----------- GENERATE HTML DASHBOARD -----------
def generate_html(certificates, secrets):
    template_html = """
    <html>
    <head>
        <title>Dev Account Certificate and Secret Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h2 { text-align: center; color: #2c3e50; }
            table { border-collapse: collapse; width: 100%; margin-bottom: 40px; }
            th, td { padding: 10px; text-align: left; border: 1px solid #ccc; }
            th { background-color: #2c3e50; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .section-title { background-color: #f39c12; padding: 10px; color: white; font-weight: bold; }
        </style>
    </head>
    <body>
        <h2>Dev Account Dashboard: ACM Certificates & Secrets</h2>

        <div class="section-title">ACM Certificates for *.dev.vapps.net</div>
        <table>
            <tr>
                <th>Domain Name</th>
                <th>Status</th>
                <th>Type</th>
                <th>Requested At</th>
                <th>Imported At</th>
                <th>Issued At</th>
                <th>Expires At</th>
                <th>Renewal Eligibility</th>
                <th>In Use By</th>
            </tr>
            {% for cert in certificates %}
            <tr>
                <td>{{ cert.DomainName }}</td>
                <td>{{ cert.Status }}</td>
                <td>{{ cert.Type }}</td>
                <td>{{ cert.RequestedAt.strftime("%Y-%m-%d") if cert.RequestedAt else "" }}</td>
                <td>{{ cert.ImportedAt.strftime("%Y-%m-%d") if cert.ImportedAt else "" }}</td>
                <td>{{ cert.IssuedAt.strftime("%Y-%m-%d") if cert.IssuedAt else "" }}</td>
                <td>{{ cert.NotAfter.strftime("%Y-%m-%d") if cert.NotAfter else "" }}</td>
                <td>{{ cert.RenewalEligibility }}</td>
                <td>{{ cert.InUseBy | join(', ') }}</td>
            </tr>
            {% endfor %}
        </table>

        <div class="section-title">Secrets: bas-chain*</div>
        <table>
            <tr>
                <th>Name</th>
                <th>Rotation Enabled</th>
                <th>Versions</th>
                <th>Replication Regions</th>
            </tr>
            {% for secret in secrets %}
            <tr>
                <td>{{ secret.Name }}</td>
                <td>{{ "Yes" if secret.RotationEnabled else "No" }}</td>
                <td>{{ secret.Versions | length }} versions</td>
                <td>
                    {% for rep in secret.ReplicationStatus %}
                        {{ rep.Region }} ({{ rep.Status }})<br/>
                    {% endfor %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    template = Template(template_html)
    return template.render(certificates=certificates, secrets=secrets)

# ----------- MAIN EXECUTION -----------
if __name__ == "__main__":
    certs = fetch_acm_certificates()
    secrets = fetch_secrets_details()
    html_output = generate_html(certs, secrets)

    with open("dev_acm_secrets_dashboard.html", "w") as f:
        f.write(html_output)

    print("✅ Dashboard generated: dev_acm_secrets_dashboard.html")
