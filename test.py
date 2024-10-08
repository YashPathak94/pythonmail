def update_kubeconfig(cluster_name, region):
    try:
        env = os.environ.copy()
        cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
        output = subprocess.check_output(cmd, shell=True, env=env).decode('utf-8').strip()
        print(output)
        # Extract the context name from the output
        context_line = [line for line in output.split('\n') if 'Added new context' in line or 'Updated context' in line]
        if context_line:
            line = context_line[0]
            # Extract the context name between 'Added new context' and 'to'
            context_name_part = line.split(' to ')[0]
            context_name = context_name_part.replace('Added new context ', '').replace('Updated context ', '').strip()
            print(f"Context name: {context_name}")
            return context_name
        else:
            print("Unable to extract context name from output.")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Error updating kubeconfig for cluster '{cluster_name}': {e.output.decode()}")
        return None
