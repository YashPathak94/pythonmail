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
