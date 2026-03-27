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
