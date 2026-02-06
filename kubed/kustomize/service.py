"""Serverless Service KRM Function

Generates Fission Package, Functions, and HTTPTriggers from a declarative Service resource.
"""

from kubed.krm import common as c
import copy
from kubed.krm.errors import plugin_fail
import zipfile
import tempfile
import base64
import hashlib
from pathlib import Path


def merge_function_config(defaults, overrides):
    """Merge function defaults with per-function overrides

    Args:
        defaults: Function defaults from spec.functionTemplate
        overrides: Per-function config from functions[n]

    Returns:
        Merged configuration with overrides taking precedence
    """
    config = copy.deepcopy(defaults)

    # Override with per-function settings
    # Note: secrets, configmaps, and triggers use no-merge logic (handled separately)
    for key in ['invokeStrategy', 'requestsPerPod', 'retainPods', 'concurrency',
                'functionTimeout', 'idletimeout', 'onceOnly', 'resources', 'podspec']:
        if key in overrides:
            config[key] = overrides[key]

    return config


def transform(krm: dict) -> dict:
    """Transform a serverless Service into Fission resources

    Generates:
    - One Package resource
    - Multiple Function resources (one per function in spec.functions)
    - Multiple HTTPTrigger resources (one per trigger)

    Args:
        krm: The KRM ResourceList containing the Service resource

    Returns:
        The ResourceList with generated Fission resources
    """
    service = krm["functionConfig"]
    metadata = service["metadata"]
    spec = service["spec"]

    # Extract common configuration
    service_name = metadata["name"]
    namespace = metadata.get("namespace", "default")
    labels = metadata.get("labels", {})

    # Package configuration
    package_spec = spec.get("package", {})
    package_name = package_spec.get("name", service_name)

    # Environment configuration
    env_spec = spec["environment"]
    env_name = env_spec["name"]
    env_namespace = env_spec.get("namespace", namespace)

    # Function defaults - these can be overridden per-function
    function_defaults = spec.get("functionTemplate", {})

    # Generate Package resource
    package = generate_package(
        name=package_name,
        namespace=namespace,
        labels=labels,
        package_spec=package_spec,
        env_name=env_name,
        env_namespace=env_namespace,
        buildcmd=package_spec.get("buildcmd")
    )
    krm["items"].append(package)

    # Validate functions list
    functions_list = spec.get("functions", [])
    if not functions_list:
        plugin_fail("Error: spec.functions must contain at least one function")

    # Validate that if name is omitted, there is only one function
    unnamed_count = sum(1 for f in functions_list if "name" not in f)
    if unnamed_count > 0 and len(functions_list) > 1:
        plugin_fail("Error: 'name' is required for each function when there are multiple functions")

    # Generate Functions and HTTPTriggers
    for func_def in spec["functions"]:
        # Default function name to service name if not provided
        short_name = func_def.get('name', service_name)

        # If function name equals service name (default), use service name directly for resource name
        # Otherwise use service-name pattern
        if short_name == service_name and "name" not in func_def:
            func_name = service_name
        else:
            func_name = f"{service_name}-{short_name}"

        # Merge function defaults with per-function overrides
        func_config = merge_function_config(function_defaults, func_def)

        # Determine secrets (no-merge logic like triggers)
        if "secrets" in func_def:
            func_secrets = func_def["secrets"]
        elif "secrets" in function_defaults:
            func_secrets = function_defaults["secrets"]
        else:
            func_secrets = []

        # Normalize secrets to include namespace
        secrets = []
        for secret in func_secrets:
            secrets.append({
                "name": secret["name"],
                "namespace": secret.get("namespace", namespace)
            })

        # Determine configmaps (no-merge logic)
        if "configmaps" in func_def:
            func_configmaps = func_def["configmaps"]
        elif "configmaps" in function_defaults:
            func_configmaps = function_defaults["configmaps"]
        else:
            func_configmaps = []

        # Normalize configmaps to include namespace
        configmaps = []
        for cm in func_configmaps:
            configmaps.append({
                "name": cm["name"],
                "namespace": cm.get("namespace", namespace)
            })

        # Generate Function resource
        function = generate_function(
            name=func_name,
            namespace=namespace,
            labels=labels,
            description=func_def.get("description"),
            function_name=func_def["functionName"],
            package_name=package_name,
            package_namespace=namespace,
            env_name=env_name,
            env_namespace=env_namespace,
            secrets=secrets,
            configmaps=configmaps,
            func_config=func_config
        )
        krm["items"].append(function)

        # Determine which triggers to use: function-level or defaults (no merge)
        if "triggers" in func_def:
            # Function has explicit triggers - use those
            triggers = func_def["triggers"]
        elif "triggers" in function_defaults:
            # Function has no triggers, use defaults
            triggers = function_defaults["triggers"]
        else:
            # No triggers at all
            triggers = []

        # Generate HTTPTrigger resources
        for trigger in triggers:
            http_trigger = generate_http_trigger(
                name=func_name,
                namespace=namespace,
                labels=labels,
                function_name=func_name,
                service_name=service_name,
                short_function_name=short_name,
                trigger_spec=trigger.get("http", {})
            )
            krm["items"].append(http_trigger)

    return krm


def generate_package(name, namespace, labels, package_spec, env_name, env_namespace, buildcmd=None):
    """Generate a Fission Package resource

    Args:
        name: Package name
        namespace: Package namespace
        labels: Labels to apply
        package_spec: Package specification from Service
        env_name: Environment name
        env_namespace: Environment namespace
        buildcmd: Optional build command

    Returns:
        Package resource dict
    """
    package = {
        "apiVersion": "fission.io/v1",
        "kind": "Package",
        "metadata": {
            "name": name,
            "namespace": namespace
        },
        "spec": {
            "environment": {
                "name": env_name,
                "namespace": env_namespace
            }
        },
        "status": {
            "buildstatus": "pending"
        }
    }

    # Add labels
    if labels:
        package["metadata"]["labels"] = copy.deepcopy(labels)

    # Add source configuration if present
    if "source" in package_spec:
        source_spec = package_spec["source"]

        # Infer source type if not specified:
        # - If 'literal' key exists, type is 'literal'
        # - If 'url' key exists, type is 'url'
        # - If 'type' is explicitly set, that takes precedence
        inferred_type = None
        if "type" in source_spec:
            inferred_type = source_spec["type"]
        elif "literal" in source_spec:
            inferred_type = "literal"
        elif "url" in source_spec:
            inferred_type = "url"

        # Handle embedded literal source - needs to be zipped and base64 encoded
        if inferred_type == "literal" and "literal" in source_spec:
            literal_code = source_spec["literal"]

            # Create a temporary directory and zip file
            with tempfile.TemporaryDirectory() as tmpdir:
                # Write the literal code to main.py
                main_py = Path(tmpdir) / "main.py"
                main_py.write_text(literal_code)

                # Create zip archive
                zip_path = Path(tmpdir) / "package.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(main_py, "main.py")

                # Read zip bytes for base64 encoding and checksum
                zip_bytes = zip_path.read_bytes()

                # Base64 encode the zip
                encoded = base64.b64encode(zip_bytes).decode('ascii')

                # Calculate checksum
                sha256_hash = hashlib.sha256(zip_bytes).hexdigest()

            # Set the source with base64 encoded zip (type defaults to literal, checksum type defaults to sha256)
            package["spec"]["source"] = {
                "type": "literal",
                "literal": encoded,
                "checksum": {
                    "type": "sha256",
                    "sum": sha256_hash
                }
            }
        else:
            # URL source - copy and normalize
            source_copy = copy.deepcopy(source_spec)

            # Infer type if not present
            if "type" not in source_copy:
                source_copy["type"] = inferred_type or "url"

            # Default checksum type to sha256 if not present
            if "checksum" in source_copy and isinstance(source_copy["checksum"], dict):
                if "type" not in source_copy["checksum"]:
                    source_copy["checksum"]["type"] = "sha256"
            

            package["spec"]["source"] = source_copy

    # Add buildcmd if present
    if buildcmd:
        package["spec"]["buildcmd"] = buildcmd

    return package


def generate_function(name, namespace, labels, description, function_name, package_name,
                      package_namespace, env_name, env_namespace, secrets, configmaps, func_config):
    """Generate a Fission Function resource

    Args:
        name: Function resource name
        namespace: Function namespace
        labels: Labels to apply
        description: Optional function description
        function_name: Entry point in package (e.g., main.handler)
        package_name: Package name
        package_namespace: Package namespace
        env_name: Environment name
        env_namespace: Environment namespace
        secrets: List of secret references
        configmaps: List of configmap references
        func_config: Merged function configuration (defaults + overrides)

    Returns:
        Function resource dict
    """
    function = {
        "apiVersion": "fission.io/v1",
        "kind": "Function",
        "metadata": {
            "name": name,
            "namespace": namespace
        },
        "spec": {
            "environment": {
                "name": env_name,
                "namespace": env_namespace
            },
            "package": {
                "packageref": {
                    "name": package_name,
                    "namespace": package_namespace
                },
                "functionName": function_name
            }
        }
    }

    # Add labels
    if labels:
        function["metadata"]["labels"] = copy.deepcopy(labels)

    # Add description annotation
    if description:
        if "annotations" not in function["metadata"]:
            function["metadata"]["annotations"] = {}
        function["metadata"]["annotations"]["kubernetes.io/description"] = description

    # Add secrets
    if secrets:
        function["spec"]["secrets"] = copy.deepcopy(secrets)

    # Add configmaps
    if configmaps:
        function["spec"]["configmaps"] = copy.deepcopy(configmaps)

    # Add InvokeStrategy (with default)
    if "invokeStrategy" in func_config:
        function["spec"]["InvokeStrategy"] = copy.deepcopy(func_config["invokeStrategy"])
    else:
        # Default InvokeStrategy (using CRD's PascalCase field names)
        function["spec"]["InvokeStrategy"] = {
            "StrategyType": "execution",
            "ExecutionStrategy": {
                "ExecutorType": "poolmgr"
            }
        }

    # Add all optional function spec fields from func_config
    # Note: secrets, configmaps, and triggers are handled separately with no-merge logic
    optional_fields = [
        'requestsPerPod',
        'retainPods',
        'concurrency',
        'functionTimeout',
        'idletimeout',
        'onceOnly',
        'resources',
        'podspec'
    ]

    for field in optional_fields:
        if field in func_config:
            function["spec"][field] = copy.deepcopy(func_config[field])

    return function


def generate_http_trigger(name, namespace, labels, function_name, service_name, short_function_name, trigger_spec):
    """Generate a Fission HTTPTrigger resource

    Args:
        name: HTTPTrigger resource name
        namespace: HTTPTrigger namespace
        labels: Labels to apply
        function_name: Function name to trigger
        service_name: Service name (for default path)
        short_function_name: Short function name (for default path)
        trigger_spec: HTTP trigger specification

    Returns:
        HTTPTrigger resource dict
    """
    # Determine default path:
    # - If path is explicitly given in trigger spec, use that (takes precedence)
    # - If function name equals service name, use /<service-name>
    # - Otherwise use /<service-name>/<function-name>
    if "path" in trigger_spec:
        path = trigger_spec["path"]
    elif short_function_name == service_name:
        path = f"/{service_name}"
    else:
        path = f"/{service_name}/{short_function_name}"

    method = trigger_spec.get("method", "GET")
    host = trigger_spec.get("host", "")

    trigger = {
        "apiVersion": "fission.io/v1",
        "kind": "HTTPTrigger",
        "metadata": {
            "name": name,
            "namespace": namespace
        },
        "spec": {
            "host": host,
            "method": method,
            "relativeurl": path,
            "functionref": {
                "type": "name",
                "name": function_name
            }
        }
    }

    # Add labels
    if labels:
        trigger["metadata"]["labels"] = copy.deepcopy(labels)

    return trigger
