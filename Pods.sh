<!DOCTYPE html>
<html>
<head>
<title>EKS Dashboard Demo</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body { font-family: Arial; margin:20px; }
h1 { text-align:center; }

.cards { display:flex; flex-wrap:wrap; gap:15px; margin-bottom:20px; }
.card { flex:1 1 180px; padding:20px; border-radius:10px; color:white; text-align:center; font-weight:bold; }

.blue{background:#007BFF;}
.green{background:#28a745;}
.orange{background:#fd7e14;}
.purple{background:#6f42c1;}
.dark{background:#343a40;}

.cluster { border:1px solid #ddd; padding:15px; margin-top:30px; border-radius:10px; }

table { width:100%; border-collapse:collapse; margin-top:20px;}
th,td{border:1px solid #ddd; padding:8px;}
th{background:#007BFF;color:white;}
</style>
</head>

<body>

<h1>EKS Dashboard (Demo)</h1>

<!-- KPI CARDS -->
<div class="cards">
<div class="card blue"><h3>Clusters</h3><p>5</p></div>
<div class="card green"><h3>Nodes</h3><p>24</p></div>
<div class="card orange"><h3>Pods</h3><p>980</p></div>

<div class="card purple"><h3>DEV Apps</h3><p>40</p></div>
<div class="card purple"><h3>IDEV Apps</h3><p>18</p></div>
<div class="card purple"><h3>INTG Apps</h3><p>30</p></div>
<div class="card dark"><h3>PROD Apps</h3><p>55</p></div>
<div class="card dark"><h3>ACCP Apps</h3><p>22</p></div>
</div>

<!-- GLOBAL CHART -->
<h2>Global Apps per Suffix</h2>
<canvas id="globalChart" height="100"></canvas>

<script>
new Chart(document.getElementById('globalChart'), {
    type:'bar',
    data:{
        labels:['dev','devb','devc'],
        datasets:[{
            label:'Applications',
            data:[40,25,15],
            backgroundColor:['#007BFF','#28a745','#fd7e14']
        }]
    }
});
</script>

<!-- CLUSTER SUMMARY -->
<h2>Cluster Summary</h2>
<table>
<tr>
<th>Cluster</th><th>Env</th><th>Nodes</th><th>Pods</th><th>Apps</th>
</tr>

<tr><td>eks-dev</td><td>dev</td><td>8</td><td>300</td><td>18</td></tr>
<tr><td>eks-idev</td><td>idev</td><td>3</td><td>100</td><td>10</td></tr>
<tr><td>eks-intg</td><td>intg</td><td>4</td><td>200</td><td>12</td></tr>
<tr><td>eks-prod</td><td>prod</td><td>6</td><td>280</td><td>20</td></tr>
<tr><td>eks-accp</td><td>accp</td><td>3</td><td>100</td><td>8</td></tr>
</table>

<!-- CLUSTER CHARTS -->

<div class="cluster">
<h3>eks-dev (dev)</h3>
<canvas id="chart1"></canvas>
<script>
new Chart(document.getElementById('chart1'), {
type:'bar',
data:{
labels:['dev','devb','devc'],
datasets:[{label:'Apps', data:[10,5,3], backgroundColor:'#007BFF'}]
}
});
</script>
</div>

<div class="cluster">
<h3>eks-intg (intg)</h3>
<canvas id="chart2"></canvas>
<script>
new Chart(document.getElementById('chart2'), {
type:'bar',
data:{
labels:['intg','intgb','intgc'],
datasets:[{label:'Apps', data:[8,6,4], backgroundColor:'#6f42c1'}]
}
});
</script>
</div>

<div class="cluster">
<h3>eks-prod (prod)</h3>
<canvas id="chart3"></canvas>
<script>
new Chart(document.getElementById('chart3'), {
type:'bar',
data:{
labels:['proda','prodb'],
datasets:[{label:'Apps', data:[12,8], backgroundColor:'#dc3545'}]
}
});
</script>
</div>

</body>
</html>



def get_deployment_count(cluster_name, aws_session):
    ctx = _kubectl_ctx(aws_session, cluster_name)

    cmd = (
        f"kubectl get deploy -A --context={ctx} "
        "-o jsonpath='{range .items[*]}{.metadata.name} {end}'"
    )

    try:
        output = subprocess.check_output(cmd, shell=True).decode().strip().split()
        return len(output)
    except:
        return 0






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
