# Advanced Service Example - GCS Source

Demonstrates advanced Service features with GCS storage, build script, and multiple functions.

## Use Case

Perfect for:
- Production functions
- Multi-endpoint services
- Functions with dependencies
- Functions needing secrets
- Teams using CI/CD

## What This Example Shows

1. **GCS Source (`type: url`)**: Package uploaded to Google Cloud Storage
2. **Build Script**: `build.sh` auto-included, runs during build
3. **Multiple Functions**: 4 different endpoints from one package
4. **Trigger Overrides**: GET (default), POST, DELETE
5. **Resource Limits**: CPU/memory constraints
6. **functionTemplate**: Shared configuration
7. **Secrets**: Kustomize secretGenerator

## File Structure

```
advanced/
├── service.yaml        # Service with GCS source
├── kustomization.yaml  # Includes secretGenerator
├── main.py             # Multiple handler functions
├── requirements.txt    # Dependencies
├── build.sh            # Build script (auto-included)
└── README.md
```

## Deploy Workflow

1. **Publish package**:
```bash
cd examples/service/advanced
kubectl fn publish .
```

This will:
- Pack main.py, requirements.txt, build.sh into zip
- Upload to GCS
- Update service.yaml with URL and checksum

2. **Deploy**:
```bash
kubectl up .
```

This will:
- Generate Secret (api-credentials)
- Generate Package, Functions, HTTPTriggers
- Trigger Fission build (runs build.sh)

## Test

```bash
# List (GET, default)
curl http://router.flow/api/list

# Get (GET, default)
curl "http://router.flow/api/get?id=123"

# Create (POST, override)
curl -X POST http://router.flow/api/create \
  -H "Content-Type: application/json" \
  -d '{"name": "test"}'

# Delete (DELETE, override)
curl -X DELETE "http://router.flow/api/delete?id=123"
```

## Generated Resources

- 1 Secret (`api-credentials` from secretGenerator)
- 1 Package (`api`)
- 4 Functions (`api-list`, `api-get`, `api-create`, `api-delete`)
- 4 HTTPTriggers

Total: 10 resources

## Key Features

### Build Script
```yaml
buildcmd: ./build.sh
```

- Auto-included in package zip
- Runs during Fission build
- Installs dependencies from requirements.txt

### functionTemplate
```yaml
functionTemplate:
  requestsPerPod: 5
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "500m"
      memory: "256Mi"
  triggers:
  - http: {}
```

All functions inherit these unless overridden.

### Per-Function Overrides
```yaml
- name: create
  triggers:
  - http:
      method: POST  # Override default GET
```

### Secrets (Kustomize)
```yaml
secretGenerator:
- name: api-credentials
  literals:
  - api_key=example-key
  - api_secret=example-secret
  options:
    disableNameSuffixHash: true
```

Referenced in service.yaml:
```yaml
secrets:
- name: api-credentials
```
