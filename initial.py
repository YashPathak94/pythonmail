import sys
import argparse
import base64
import os
from kubernetes import client, config
from termcolor import colored
from tabulate import tabulate
from typing import List, ByteString
from pepipost.pepipost_client import PepipostClient
from pepipost.configuration import Configuration
from pepipost.models.send import Send
from pepipost.models.mfrom import From
from pepipost.models.content import Content
from pepipost.models.type_enum import TypeEnum
from pepipost.models.attachments import Attachments
from pepipost.models.personalizations import Personalizations
from pepipost.models.email_struct import EmailStruct
from pepipost.models.settings import Settings
from pepipost.exceptions.api_exception import APIException

# Existing code for generating the report
def get_pod_data(api_instance, cluster_name):
    all_pods_data = []
    
    namespaces = api_instance.list_namespace()

    for namespace in namespaces.items:
        api_instance = client.CoreV1Api()
        namespace_name = namespace.metadata.name

        all_pods = api_instance.list_namespaced_pod(namespace=namespace_name)
        total_pods = len(all_pods.items)
        running_pods = sum(1 for pod in all_pods.items if pod.status.phase == "Running")

        if total_pods == 0 and running_pods == 0:
            namespace_status = "In Progress"
        else:
            namespace_status = "All Pods Running" if running_pods == total_pods else "Some Pods Not Running"
            namespace_status = colored(namespace_status, "green" if running_pods == total_pods else "red")

        all_pods_data.append([cluster_name, namespace_name, total_pods, running_pods, namespace_status])

    return all_pods_data

def main():
    try:
        config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {str(e)}")
        sys.exit(1)

    api_instance = client.CoreV1Api()

    # Set the cluster name manually
    cluster_name = "xyz"

    # Generate the report and save it as a CSV
    pod_data = get_pod_data(api_instance, cluster_name)

    # Convert the pod data to CSV and save it
    csv_filename = "pod_data.csv"
    with open(csv_filename, 'w') as csv_file:
        for row in pod_data:
            csv_file.write(','.join(map(str, row)) + '\n')

    # Send the email with the CSV attachment using Pepipost
    from_email = "your-email@example.com"  # Set your sender email here
    from_name = "Your Name"
    to = ["recipient@example.com"]  # Set the recipient's email here
    reply_to = "no-reply@example.com"
    subject = "Kubernetes Pod Report"
    body = "Please find the attached Kubernetes Pod Report."

    attachment = Attachment(name="pod_data.csv", data=open(csv_filename, 'rb').read())

    email_dto = EmailDto(
        from_email=from_email,
        from_name=from_name,
        to=to,
        reply_to=reply_to,
        subject=subject,
        body=body,
        attachments=[attachment])

    # Send the email with the CSV attachment using Pepipost
    api_key = "YOUR_API_KEY"  # Replace with your Pepipost API key
    send_email(email_dto, api_key)

if __name__ == "__main__":
    main()
