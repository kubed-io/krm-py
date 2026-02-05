# Fission Service Generator

Generates Fission Package, Functions, and HTTPTriggers from a single declarative Service resource.

## Overview

The Service generator (`serverless.krm.kubed.io/v1`) replaces multiple individual YAML files with a single declarative resource that:

- Defines one Package with source URL, build command, and include patterns
- Declares multiple Functions with different entry points
- Configures HTTP triggers with smart defaults
- Uses `functionTemplate` for cascading configuration (DRY principle)
- Automatically generates all Fission resources via Kustomize

**Before**: 1 package.yaml + N function-*.yaml files (3-10+ files)
**After**: 1 service.yaml (generates everything)

## Basic Example

```yaml
# yaml-language-server: $schema=../../../krm-py/spec/service.schema.json
apiVersion: serverless.krm.kubed.io/v1
kind: Service
metadata:
  name: myservice
  namespace: flow
  labels:
    app: myservice
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  package:
    include:
    - '*.py'
    - requirements.txt
    source:
      type: url
      url: https://storage.googleapis.com/kellyferrone-functions/myservice-20260205214611.zip
      checksum:
        type: sha256
        sum: abc123...
    buildcmd: ./build.sh
  environment:
    name: python
  secrets:
  - name: my-secret
  functionTemplate:
    requestsPerPod: 5
    triggers:
    - http: {}
  functions:
  - name: handler1
    functionName: main.get_data
  - name: handler2
    functionName: main.post_data
```

## Generated Resources

From the above service.yaml, the generator creates:

1. **One Package**:
```yaml
apiVersion: fission.io/v1
kind: Package
metadata:
  name: myservice
  namespace: flow
  labels:
    app: myservice
spec:
  environment:
    name: python
    namespace: flow
  source:
    type: url
    url: https://storage.googleapis.com/.../myservice.zip
    checksum:
      type: sha256
      sum: abc123...
  buildcmd: ./build.sh
status:
  buildstatus: pending
```

2. **Two Functions** (myservice-handler1, myservice-handler2):
```yaml
apiVersion: fission.io/v1
kind: Function
metadata:
  name: myservice-handler1
  namespace: flow
  labels:
    app: myservice
spec:
  environment:
    name: python
    namespace: flow
  package:
    functionName: main.get_data
    packageref:
      name: myservice
      namespace: flow
  secrets:
  - name: my-secret
    namespace: flow
  requestsPerPod: 5
  InvokeStrategy:
    StrategyType: execution
    ExecutionStrategy:
      ExecutorType: poolmgr
```

3. **Two HTTPTriggers** (myservice-handler1, myservice-handler2):
```yaml
apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: myservice-handler1
  namespace: flow
  labels:
    app: myservice
spec:
  host: ""
  method: GET
  relativeurl: /myservice/handler1
  functionref:
    type: name
    name: myservice-handler1
```

## Specification

### metadata

```yaml
metadata:
  name: service-name          # Required: Service name (kebab-case)
  namespace: flow              # Optional: Defaults to flow
  labels:                      # Optional: Propagated to all generated resources
    app: myservice
  annotations:                 # Optional: Not propagated
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
```

**Note**: Labels are propagated to all generated resources (Package, Functions, HTTPTriggers).

### spec.package

```yaml
spec:
  package:
    name: custom-name         # Optional: Defaults to service name
    include:                  # Optional: Glob patterns, defaults to ['*.py']
    - '*.py'
    - requirements.txt
    - config/*.json
    source:
      type: url               # Required: Always 'url' for GCS
      url: https://...        # Required: Set by kubectl fn publish
      checksum:
        type: sha256
        sum: abc123...
    buildcmd: ./build.sh      # Optional: Build script (auto-included in zip)
```

**Important**: The file specified in `buildcmd` is automatically included in the package zip, even if not matched by `include` patterns.

### spec.environment

```yaml
spec:
  environment:
    name: python              # Required: Environment name
    namespace: flow           # Optional: Defaults to service namespace
```

### spec.secrets

```yaml
spec:
  secrets:
  - name: my-secret           # Required: Secret name
    namespace: flow           # Optional: Defaults to service namespace
```

Secrets are mounted at `/secrets/<namespace>/<secret-name>/<key>`.

### spec.functionTemplate

Cascading configuration applied to all functions unless overridden:

```yaml
spec:
  functionTemplate:
    requestsPerPod: 5
    retainPods: 3
    concurrency: 10
    functionTimeout: 120
    idletimeout: 300
    onceOnly: false
    resources:
      requests:
        cpu: "100m"
        memory: "128Mi"
      limits:
        cpu: "1"
        memory: "512Mi"
    configmaps:
    - name: my-config
      namespace: flow
    podspec:
      serviceAccountName: my-sa
    invokeStrategy:
      StrategyType: execution
      ExecutionStrategy:
        ExecutorType: poolmgr
    triggers:
    - http: {}
```

**Supported fields**:
- `invokeStrategy` - Execution strategy (default: poolmgr)
- `requestsPerPod` - Requests before pod refresh (integer, minimum 1)
- `retainPods` - Minimum pod count (integer, minimum 0, default 0)
- `concurrency` - Max concurrent requests (integer)
- `functionTimeout` - Timeout in seconds (integer)
- `idletimeout` - Idle timeout in seconds (integer)
- `onceOnly` - Run once then terminate (boolean)
- `resources` - CPU/memory requests/limits
- `configmaps` - ConfigMap references
- `podspec` - Custom pod spec
- `triggers` - Default HTTP triggers

### spec.functions

```yaml
spec:
  functions:
  - name: handler1            # Required: Short function name (kebab-case)
    functionName: main.handler1  # Required: Entry point (module.function)
    description: "Handler description"  # Optional: Becomes kubernetes.io/description
    requestsPerPod: 10        # Optional: Override default
    triggers:                 # Optional: Override default (no merge)
    - http:
        method: POST
        path: /custom/path
```

**Per-function overrides**: Any field from `functionTemplate` can be overridden at the function level.

### Trigger Behavior (No-Merge Logic)

Triggers use **no-merge logic** for predictability:

- **Function has `triggers` key**: Use function's triggers (even if empty = no HTTP endpoint)
- **Function lacks `triggers` key AND defaults exist**: Use `functionTemplate.triggers`
- **Otherwise**: No triggers generated

```yaml
functionTemplate:
  triggers:
  - http: {}           # Default GET /<service>/<function>

functions:
- name: uses-default   # Gets default trigger
  functionName: main.handler1

- name: custom         # Overrides with custom trigger
  functionName: main.handler2
  triggers:
  - http:
      method: POST
      path: /custom

- name: no-trigger     # Explicitly has no HTTP endpoint
  functionName: main.handler3
  triggers: []
```

### HTTP Trigger Specification

```yaml
triggers:
- http:
    method: GET              # Optional: Default GET
    path: /custom/path       # Optional: Default /<service>/<function>
    host: example.com        # Optional: Host header match
    prefix: /api             # Optional: Path prefix
    ingressConfig:           # Optional: Ingress configuration
      annotations:
        cert-manager.io/cluster-issuer: letsencrypt
      path: /external
      host: api.example.com
      tls: tls-secret
```

**Smart defaults**: Empty `http: {}` expands to:
- `method: GET`
- `path: /<service>/<function>`
- `host: ""`

## InvokeStrategy

```yaml
invokeStrategy:
  StrategyType: execution    # Required: execution or newdeploy
  ExecutionStrategy:
    ExecutorType: poolmgr    # Required: poolmgr or newdeploy
    MinScale: 1              # Optional (newdeploy only)
    MaxScale: 10             # Optional (newdeploy only)
    TargetCPUPercent: 80     # Optional (newdeploy only)
```

**Note**: Field names use PascalCase (`StrategyType`, `ExecutionStrategy`, `ExecutorType`) per Fission CRD spec.

**Default**: If not specified, defaults to:
```yaml
InvokeStrategy:
  StrategyType: execution
  ExecutionStrategy:
    ExecutorType: poolmgr
```

## kubectl fn Commands

### publish

Pack source files and publish to GCS:

```bash
kubectl fn publish functions/<name>
kubectl fn publish <path>/service.yaml
```

**What it does**:
1. Reads `include` patterns and `buildcmd` from service.yaml
2. Packs matching files into timestamped zip (e.g., `myservice-20260205214611.zip`)
3. Auto-includes `buildcmd` file (e.g., `build.sh`)
4. Uploads to GCS: `gs://kellyferrone-functions/<zip>`
5. Sets public-read ACL
6. Updates service.yaml with new URL and SHA256 checksum
7. Prints deploy command: `kubectl up <dir>`

**Options**:
- `-b, --bucket` - Override GCS bucket (default: `$FX_BUCKET` or `kellyferrone-functions`)

### pack

Pack source files into zip without publishing:

```bash
kubectl fn pack functions/<name>
kubectl fn pack <path>/service.yaml -o /tmp/test.zip
```

**Options**:
- `-o, --out` - Output path (default: `/tmp/<package>-<timestamp>.zip`)

## Naming Conventions

- **Service name**: kebab-case (e.g., `monarch`, `my-service`)
- **Function name**: short kebab-case (e.g., `accounts`, `get-data`)
- **Generated resource name**: `<service>-<function>` (e.g., `monarch-accounts`)
- **Default HTTP path**: `/<service>/<function>` (e.g., `/monarch/accounts`)
- **Namespace**: Always `flow`
- **Entry points**: `main.<function_name>` (e.g., `main.get_accounts`)

## Complete Example: Monarch Money

```yaml
# yaml-language-server: $schema=../../../krm-py/spec/service.schema.json
apiVersion: serverless.krm.kubed.io/v1
kind: Service
metadata:
  name: monarch
  namespace: flow
  labels:
    app: monarch
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  package:
    include:
    - '*.py'
    - requirements.txt
    source:
      type: url
      url: https://storage.googleapis.com/kellyferrone-functions/monarch-20260205214611.zip
      checksum:
        type: sha256
        sum: 9cba339316b6092e7d0e25d86c56f5e6cc30def0c0204eec4895fb6c13164624
    buildcmd: ./build.sh
  environment:
    name: python
  secrets:
  - name: monarch-money
  functionTemplate:
    requestsPerPod: 5
    triggers:
    - http: {}
  functions:
  - name: accounts
    functionName: main.get_accounts
  - name: institutions
    functionName: main.get_institutions
  - name: budgets
    functionName: main.get_budgets
  - name: transactions
    functionName: main.get_transactions
```

**Generated**: 1 Package + 4 Functions + 4 HTTPTriggers = 9 resources

**Endpoints**:
- `GET /monarch/accounts`
- `GET /monarch/institutions`
- `GET /monarch/budgets`
- `GET /monarch/transactions`

## VSCode Autocomplete

Add this comment at the top of service.yaml for schema validation and autocomplete:

```yaml
# yaml-language-server: $schema=../../../krm-py/spec/service.schema.json
```

The path is relative from service.yaml to `/projects/krm-py/spec/service.schema.json`.

**Features**:
- Field autocomplete
- Type validation
- Required field highlighting
- Hover documentation

**Requirements**: [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for VSCode

## See Also

- Generator implementation: `/projects/krm-py/kubed/kustomize/service.py`
- kubectl-fn implementation: `/projects/krm-py/kubed/kubectl/fn.py`
- JSON schema: `/projects/krm-py/spec/service.schema.json`
- Example: `/projects/cluster/functions/monarch/`
- Skill documentation: `/projects/cluster/.claude/skills/fission-function/SKILL.md`
