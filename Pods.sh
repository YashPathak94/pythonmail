def detect_pod_colocation(cluster_name, aws_session):
    alerts = []

    ctx = _kubectl_ctx(aws_session, cluster_name)

    cmd = f"""
    kubectl get pods -A --context={ctx} \
    -o jsonpath='{{range .items[*]}}{{.metadata.namespace}}|{{.metadata.name}}|{{.spec.nodeName}} {{end}}'
    """

    try:
        output = subprocess.check_output(cmd, shell=True).decode().strip().split()
    except:
        return alerts

    # structure: { (ns, app) : {node: count} }
    app_node_map = {}

    for line in output:
        try:
            ns, pod, node = line.split('|')

            # Extract app name (remove random suffix)
            app = "-".join(pod.split('-')[:-2])

            key = (ns, app)

            if key not in app_node_map:
                app_node_map[key] = {}

            app_node_map[key][node] = app_node_map[key].get(node, 0) + 1

        except:
            continue

    # detect duplicates
    for (ns, app), nodes in app_node_map.items():
        for node, count in nodes.items():
            if count > 1:
                alerts.append({
                    'namespace': ns,
                    'app': app,
                    'node': node,
                    'count': count
                })

    return alerts


<div style="background:#ff4d4d;color:white;padding:15px;border-radius:8px;margin-bottom:20px;">

<h3>🚨 Alerts (Pod Co-location Issue)</h3>

{% if global_alerts|length == 0 %}
<p>No issues detected ✅</p>
{% else %}
<ul>
{% for a in global_alerts %}
<li>
⚠️ {{ a.app }} ({{ a.namespace }}) → {{ a.count }} pods on same node {{ a.node }}

<a href="#env-{{ a.env }}" style="color:white;font-weight:bold;">
👉 Go to {{ a.env }}
</a>

</li>
{% endfor %}
</ul>
{% endif %}

</div>

{% if c.alerts %}
<h4 style="color:red;">⚠️ Pod Placement Issues</h4>
<table>
<tr>
<th>Namespace</th>
<th>Application</th>
<th>Node</th>
<th>Pods Count</th>
</tr>

{% for a in c.alerts %}
<tr>
<td>{{ a.namespace }}</td>
<td>{{ a.app }}</td>
<td>{{ a.node }}</td>
<td>{{ a.count }}</td>
</tr>
{% endfor %}
</table>
{% endif %}





kubectl get pods -A -o wide --no-headers | awk '{print $8, $2}' | sort | \
awk '
{
  node=$1
  pod=$2
  pods[node]=pods[node]" "pod
}
END {
  for (n in pods) {
    print "Node:", n
    print "Pods:", pods[n]
    print "----------------------"
  }
}'



kubectl get pods -A -o json | jq -r '
.items[] |
"\(.metadata.labels.app) \(.spec.nodeName) \(.metadata.name)"' | sort | \
awk '
{
  key=$1" "$2
  pods[key]=pods[key]" "$3
  count[key]++
}
END {
  for (k in pods) {
    if (count[k] > 1) {
      print "Same app on same node:", k
      print "Pods:", pods[k]
      print "---------------------"
    }
}'

kubectl get pods -A -o json | jq -r '
.items[] |
"\(.metadata.namespace)\t\(.metadata.labels.app // "NULL")\t\(.spec.nodeName)\t\(.metadata.name)"
' | sort | awk '
BEGIN {
  GREEN="\033[32m";
  YELLOW="\033[33m";
  BLUE="\033[34m";
  RESET="\033[0m";

  printf "%-20s %-25s %-30s %-50s\n", "NAMESPACE", "APP", "NODE", "POD"
  print "--------------------------------------------------------------------------------------------------------------------------"
}
{
  ns=$1
  app=$2
  node=$3
  pod=$4

  key=app"|"node
  count[key]++

  data[NR]=$0
}
END {
  for (i=1; i<=NR; i++) {
    split(data[i], f, "\t")
    ns=f[1]; app=f[2]; node=f[3]; pod=f[4]
    key=app"|"node

    # App coloring
    app_color=app
    if (app=="NULL") {
      app_color=GREEN app RESET
    } else if (count[key] > 1) {
      app_color=BLUE app RESET
    }

    # Pod coloring
    pod_color=pod
    if (pod ~ /proda/) {
      pod_color=GREEN pod RESET
    } else if (pod ~ /prodb/) {
      pod_color=YELLOW pod RESET
    }

    printf "%-20s %-25s %-30s %-50s\n", ns, app_color, node, pod_color
  }
}'



kubectl get pods -A -o json | jq -r '
.items[] |
[
  .metadata.namespace,
  (.metadata.ownerReferences[0].name // "no-owner"),
  .spec.nodeName,
  .metadata.name
] | @tsv
' | sed -E 's/-[a-z0-9]{9,10}$//' | sort | awk '
BEGIN {
  RED="\033[31m";
  GREEN="\033[32m";
  YELLOW="\033[33m";
  BLUE="\033[34m";
  RESET="\033[0m";

  printf "%-20s %-35s %-30s %-50s\n", "NAMESPACE", "DEPLOYMENT", "NODE", "POD"
  print "----------------------------------------------------------------------------------------------------------------------------------"
}
{
  ns=$1
  deploy=$2
  node=$3
  pod=$4

  key=deploy"|"node
  count[key]++

  data[NR]=$0
}
END {
  for (i=1; i<=NR; i++) {
    split(data[i], f, "\t")
    ns=f[1]; deploy=f[2]; node=f[3]; pod=f[4]
    key=deploy"|"node

    # 🔴 Highlight same deployment pods on same node
    deploy_color=deploy
    if (count[key] > 1 && deploy != "no-owner") {
      deploy_color=RED deploy RESET
    }

    # Pod color rules
    pod_color=pod
    if (pod ~ /proda/) {
      pod_color=GREEN pod RESET
    } else if (pod ~ /prodb/) {
      pod_color=YELLOW pod RESET
    }

    printf "%-20s %-35s %-30s %-50s\n", ns, deploy_color, node, pod_color
  }
}'


kubectl get pods -A -o json | jq -r '
.items[] |
[
  .metadata.namespace,
  (.metadata.ownerReferences[0].name // "no-owner"),
  .spec.nodeName,
  .metadata.name
] | @tsv
' | sed -E 's/-[a-z0-9]{9,10}$//' | sort | \
awk -F '\t' '
BEGIN {
  RED="\033[31m";
  GREEN="\033[32m";
  YELLOW="\033[33m";
  RESET="\033[0m";

  # Header
  printf "%-20s %-40s %-35s %-50s\n", "NAMESPACE", "DEPLOYMENT", "NODE", "POD";
  printf "%-20s %-40s %-35s %-50s\n", "-------------------", "--------------------------------------", "-----------------------------------", "--------------------------------------------------";
}
{
  ns=$1
  deploy=$2
  node=$3
  pod=$4

  key=deploy"|"node
  count[key]++

  data[NR]=$0
}
END {
  for (i=1; i<=NR; i++) {
    split(data[i], f, "\t")
    ns=f[1]; deploy=f[2]; node=f[3]; pod=f[4]
    key=deploy"|"node

    # 🔴 Same deployment on same node
    deploy_color=deploy
    if (count[key] > 1 && deploy != "no-owner") {
      deploy_color=RED deploy RESET
    }

    # Pod coloring
    pod_color=pod
    if (pod ~ /proda/) {
      pod_color=GREEN pod RESET
    } else if (pod ~ /prodb/) {
      pod_color=YELLOW pod RESET
    }

    printf "%-20s %-40s %-35s %-50s\n", ns, deploy_color, node, pod_color
  }
}'



<!DOCTYPE html>
<html>
<head>
<title>EKS Dashboard Demo</title>

<style>
body { font-family: Arial; margin: 20px; }

.cards {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
}

.card {
    flex: 1 1 180px;
    padding: 20px;
    border-radius: 10px;
    color: white;
    text-align: center;
    font-weight: bold;
}

.blue { background: #007BFF; }
.green { background: #28a745; }
.orange { background: #fd7e14; }
.purple { background: #6f42c1; }
.dark { background: #343a40; }

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 30px;
}

th, td {
    border: 1px solid #ddd;
    padding: 10px;
}

th {
    background: #007BFF;
    color: white;
}
</style>

</head>

<body>

<h1>Venerable EKS Dashboard</h1>

<!-- CARDS -->
<div class="cards">

    <div class="card blue">
        <h3>Total Clusters</h3>
        <p>6</p>
    </div>

    <div class="card green">
        <h3>Total Nodes</h3>
        <p>32</p>
    </div>

    <div class="card orange">
        <h3>Total Pods</h3>
        <p>1262</p>
    </div>

    <div class="card purple">
        <h3>DEV Apps</h3>
        <p>45</p>
    </div>

    <div class="card purple">
        <h3>IDEV Apps</h3>
        <p>20</p>
    </div>

    <div class="card purple">
        <h3>INTG Apps</h3>
        <p>30</p>
    </div>

    <div class="card dark">
        <h3>PROD Apps</h3>
        <p>60</p>
    </div>

    <div class="card dark">
        <h3>ACCP Apps</h3>
        <p>25</p>
    </div>

</div>

<!-- TABLE -->
<h2>Cluster Summary</h2>

<table>
<tr>
<th>Cluster</th>
<th>Env</th>
<th>Region</th>
<th>Nodes</th>
<th>Pods</th>
<th>Applications</th>
</tr>

<tr>
<td>venerable-eks-dev</td>
<td>dev</td>
<td>us-east-1</td>
<td>11</td>
<td>320</td>
<td>15</td>
</tr>

<tr>
<td>ven-eks-idev</td>
<td>idev</td>
<td>us-east-1</td>
<td>4</td>
<td>120</td>
<td>10</td>
</tr>

<tr>
<td>venerable-eks-intg</td>
<td>intg</td>
<td>us-east-1</td>
<td>5</td>
<td>200</td>
<td>12</td>
</tr>

<tr>
<td>venerable-eks-prod</td>
<td>prod</td>
<td>us-east-1</td>
<td>4</td>
<td>350</td>
<td>20</td>
</tr>

<tr>
<td>venerable-eks-accp</td>
<td>accp</td>
<td>us-east-1</td>
<td>8</td>
<td>250</td>
<td>18</td>
</tr>

<tr>
<td>venerable-eks-dr</td>
<td>dr</td>
<td>us-west-2</td>
<td>0</td>
<td>22</td>
<td>5</td>
</tr>

</table>

</body>
</html>
