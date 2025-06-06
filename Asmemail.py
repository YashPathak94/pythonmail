
import boto3
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# --- CONFIGURATION ---

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

# Email config
sender_email = "your_email@example.com"
receiver_emails = ["recipient1@example.com"]
subject = "AWS ACM & Secrets Expiry Dashboard"
smtp_server = "smtp.example.com"
smtp_port = 587
smtp_user = "your_email@example.com"
smtp_password = "your_password"

# --- FUNCTIONS ---

def format_date(dt):
    return dt.strftime('%Y-%m-%d') if dt else "-"

def days_until(expiry_date):
    return (expiry_date - datetime.utcnow()).days if expiry_date else "-"

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
                expiry = cert_details.get('NotAfter')

                cert_data = {
                    'DomainName': domain_name,
                    'Status': cert_details.get('Status'),
                    'Type': cert_details.get('Type'),
                    'RequestedAt': format_date(cert_details.get('CreatedAt')),
                    'ImportedAt': format_date(cert_details.get('ImportedAt')),
                    'IssuedAt': format_date(cert_details.get('IssuedAt')),
                    'NotAfter': format_date(expiry),
                    'DaysRemaining': days_until(expiry),
                    'RenewalEligibility': cert_details.get('RenewalEligibility', "-"),
                    'InUseBy': cert_details.get('InUseBy', [])
                }
                certificates_data.append(cert_data)
            except Exception:
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
            except Exception:
                continue
    return secrets_data

def generate_html_report(all_data):
    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>ACM & Secrets Dashboard</title>
    <style>body{font-family:sans-serif;}h2{background:#444;color:#fff;padding:10px;}
    table{width:100%;border-collapse:collapse;margin-bottom:30px;}
    th,td{border:1px solid #ccc;padding:8px;}th{background:#222;color:#fff;}
    details summary{cursor:pointer;font-weight:bold;}</style></head><body>
    <h1>ACM Certificates & Secrets Dashboard</h1>"""
    for env, data in all_data.items():
        html += f"""<h2>{env.upper()} - Certificates</h2><table>
        <tr><th>Domain</th><th>Status</th><th>Type</th><th>Expires At</th><th>Days Left</th><th>In Use By</th></tr>"""
        for cert in data['certs']:
            html += f"""<tr><td>{cert['DomainName']}</td><td>{cert['Status']}</td>
            <td>{cert['Type']}</td><td>{cert['NotAfter']}</td><td>{cert['DaysRemaining']}</td>
            <td><details><summary>{len(cert['InUseBy'])} resources</summary><ul>"""
            for r in cert['InUseBy']:
                html += f"<li>{r}</li>"
            html += "</ul></details></td></tr>"
        html += "</table><h2>{env.upper()} - Secrets</h2><table><tr><th>Name</th><th>Rotation</th><th>Versions</th><th>Replication</th></tr>"
        for secret in data['secrets']:
            html += f"<tr><td>{secret['Name']}</td><td>{secret['RotationEnabled']}</td><td>{secret['Versions']}</td><td>{secret['ReplicationRegions']}</td></tr>"
        html += "</table>"
    html += "</body></html>"
    with open("acm_secrets_multi_account_dashboard.html", "w") as f:
        f.write(html)
    return html

def generate_email_summary(all_data):
    body = "Summary of ACM Certificate Expirations:\n\n"
    for env, data in all_data.items():
        body += f"Environment: {env.upper()}\n"
        for cert in data['certs']:
            body += f" - {cert['DomainName']} expires in {cert['DaysRemaining']} days (on {cert['NotAfter']})\n"
        body += "\n"
    return body

def send_email(html_content, summary_text):
    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = ", ".join(receiver_emails)
    msg["Subject"] = subject

    msg.attach(MIMEText(summary_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(sender_email, receiver_emails, msg.as_string())
    print("âœ… Email sent successfully.")

# --- MAIN EXECUTION ---

def main():
    all_account_data = {}
    for env, config in accounts.items():
        session = boto3.Session(
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"],
            aws_session_token=config["aws_session_token"],
            region_name=config["region"]
        )
        certs = fetch_acm_data(session, config["region"], config["domain_filter"])
        secrets = fetch_secrets_data(session, config["region"], config["secret_prefix"])
        all_account_data[env] = {"certs": certs, "secrets": secrets}

    html_report = generate_html_report(all_account_data)
    summary = generate_email_summary(all_account_data)
    send_email(html_report, summary)

if __name__ == "__main__":
    main()
