def get_pods_and_metrics(account):
    pods = []
    namespace_counts = {}
    suffixes = suffixes_map.get(account['name'], [])
    if account['name'] in ['idev', 'dr']:
        group_counts = {'total': 0}
        group_order = ['total']
    else:
        group_counts = {suffix: 0 for suffix in suffixes}
        group_counts['others'] = 0
        group_order = suffixes + ['others']

    try:
        env = os.environ.copy()
        cmd = (
            f"kubectl get pods --all-namespaces --context {account['context']} "
            f"-o jsonpath='{{range .items[*]}}{{.metadata.namespace}}|{{.metadata.name}}|{{.spec.nodeName}} {{end}}'"
        )
        pod_info_output = subprocess.check_output(cmd, shell=True, env=env).decode('utf-8').strip()

        if not pod_info_output:
            print(f"No pods found in cluster '{account['name']}'")
            return pods, namespace_counts, group_counts, group_order

        pod_info = pod_info_output.split()

        for pod in pod_info:
            try:
                namespace, pod_name, node_name = pod.split('|')

                # Debug prints
                print(f"Raw pod_name: '{pod_name}'")
                print(f"Raw node_name: '{node_name}'")

                # Ensure pod_name and node_name do not include slashes
                pod_name = pod_name.split('/')[-1]
                node_name = node_name.split('/')[-1] if node_name else ''

                print(f"Processed pod_name: '{pod_name}'")
                print(f"Processed node_name: '{node_name}'")

                # Increment namespace count
                namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1

                # Process group counts
                if account['name'] in ['idev', 'dr']:
                    group_counts['total'] += 1
                else:
                    matched = False
                    for suffix in suffixes:
                        if namespace.endswith(suffix):
                            group_counts[suffix] += 1
                            matched = True
                            break
                    if not matched:
                        group_counts['others'] += 1

                # Get pod metrics
                cpu_cmd = (
                    f"kubectl top pod {pod_name} --namespace={namespace} --context {account['context']} "
                    f"--no-headers | awk '{{print $2}}'"
                )
                cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True, env=env).decode('utf-8').strip()

                memory_cmd = (
                    f"kubectl top pod {pod_name} --namespace={namespace} --context {account['context']} "
                    f"--no-headers | awk '{{print $3}}'"
                )
                memory_utilization_raw = subprocess.check_output(memory_cmd, shell=True, env=env).decode('utf-8').strip()

                # Process CPU and memory utilization
                cpu_utilization = parse_cpu_utilization(cpu_utilization_raw)
                memory_utilization_gb, _ = parse_memory_utilization(memory_utilization_raw, 1)

                pods.append({
                    'namespace': namespace,
                    'name': pod_name,
                    'node_name': node_name,
                    'cpu_utilization': f"{cpu_utilization:.2f}",
                    'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
                })

            except ValueError as e:
                print(f"Error processing pod data: {pod}. Error: {e}")
                continue

    except subprocess.CalledProcessError as e:
        print(f"Error fetching pods for cluster '{account['name']}': {e.output.decode()}")

    return pods, namespace_counts, group_counts, group_order



def get_nodes_and_metrics(account):
    nodes = []
    try:
        env = os.environ.copy()
        cmd = (
            f"kubectl get nodes --context {account['context']} "
            f"-o jsonpath='{{range .items[*]}}{{.metadata.name}}|{{.status.capacity.cpu}}|{{.status.capacity.memory}} {{end}}'"
        )
        node_info_output = subprocess.check_output(cmd, shell=True, env=env).decode('utf-8').strip()

        if not node_info_output:
            print(f"No nodes found in cluster '{account['name']}'")
            return nodes

        node_info = node_info_output.split()

        for node in node_info:
            node_details = node.split('|')
            if len(node_details) != 3:
                print(f"Unexpected node data format: {node_details}")
                continue

            node_name, cpu_capacity, memory_capacity = node_details

            # Debug print
            print(f"Raw node_name: '{node_name}'")

            # Ensure node_name does not include slashes
            node_name = node_name.split('/')[-1]

            print(f"Processed node_name: '{node_name}'")

            memory_capacity_value = memory_capacity[:-2]  # Remove unit
            memory_unit = memory_capacity[-2:]

            # Convert memory capacity to GB
            if memory_unit == 'Ki':
                memory_capacity_gb = int(memory_capacity_value) / (1024 ** 2)
            elif memory_unit == 'Mi':
                memory_capacity_gb = int(memory_capacity_value) / 1024
            elif memory_unit == 'Gi':
                memory_capacity_gb = int(memory_capacity_value)
            else:
                memory_capacity_gb = int(memory_capacity_value) / (1024 ** 3)

            # Get node metrics
            cpu_cmd = f"kubectl top node {node_name} --context {account['context']} --no-headers | awk '{{print $2}}'"
            cpu_utilization_raw = subprocess.check_output(cpu_cmd, shell=True, env=env).decode('utf-8').strip()

            memory_cmd = f"kubectl top node {node_name} --context {account['context']} --no-headers | awk '{{print $4}}'"
            memory_utilization_raw = subprocess.check_output(memory_cmd, shell=True, env=env).decode('utf-8').strip()

            # Process CPU and memory utilization
            cpu_utilization = parse_cpu_utilization(cpu_utilization_raw)
            memory_utilization_gb, memory_utilization_percentage = parse_memory_utilization(
                memory_utilization_raw, memory_capacity_gb
            )

            nodes.append({
                'name': node_name,
                'cpu_capacity': cpu_capacity,
                'memory_capacity_gb': f"{memory_capacity_gb:.2f} GB",
                'cpu_utilization': f"{cpu_utilization:.2f}",
                'memory_utilization_gb': f"{memory_utilization_gb:.2f} GB",
                'memory_utilization_percentage': f"{memory_utilization_percentage:.2f}"
            })

    except subprocess.CalledProcessError as e:
        print(f"Error fetching nodes for cluster '{account['name']}': {e.output.decode()}")

    return nodes
