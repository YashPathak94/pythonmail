#!/bin/bash

CLUSTER_NAME="<cluster-name>"

echo "EKS Cluster Version:"
aws eks describe-cluster --name "$CLUSTER_NAME" --query "cluster.version" --output text

echo -e "\nEKS Add-ons:"
aws eks list-addons --cluster-name "$CLUSTER_NAME"

echo -e "\nMetrics Server Version:"
kubectl get pods -n kube-system -o json | jq '.items[] | select(.metadata.labels.app=="metrics-server") | .spec.containers[0].image'

echo -e "\nNGINX Ingress Version:"
kubectl get pods -n ingress-nginx -o json | jq '.items[] | select(.metadata.labels.app.kubernetes.io/name=="ingress-nginx") | .spec.containers[0].image'

echo -e "\nFluent Bit Version:"
kubectl get pods -n fluent-bit -o json | jq '.items[] | select(.metadata.labels.app=="fluent-bit") | .spec.containers[0].image'

echo -e "\nAll kube-system Pod Versions:"
kubectl get pods -n kube-system -o json | jq '.items[] | {name: .metadata.name, image: .spec.containers[].image}'
