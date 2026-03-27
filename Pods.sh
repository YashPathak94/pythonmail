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
