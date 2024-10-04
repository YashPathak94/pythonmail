def set_aws_credentials(environment):
    """
    Dynamically set AWS credentials in the environment for the given environment.
    For 'dr', use the same credentials as 'prod'.
    """
    if environment == 'dr':
        environment = 'prod'  # Use 'prod' credentials for 'dr'

    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv(f'{environment}_AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv(f'{environment}_AWS_SECRET_ACCESS_KEY')
    
    # Only set AWS_SESSION_TOKEN if it's not None
    session_token = os.getenv(f'{environment}_AWS_SESSION_TOKEN')
    if session_token:
        os.environ['AWS_SESSION_TOKEN'] = session_token

    # Check for missing credentials
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        print(f"Error: AWS credentials for {environment} are not set correctly.")
        sys.exit(1)

    print(f"Using credentials for environment: {environment}")
