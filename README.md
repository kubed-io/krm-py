# Kubed KRM

A python Implementation of KRM function by Kustomize and Google.

## Random

Generate a random string or number and stamp it into target resource fields.
Configure `keepers` and the value is deterministically derived from the
keeper field values — same inputs, same output — like Terraform's
[`random_string`](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string).
Useful for getting a Job name that only changes when upstream values
actually change (a workaround for Kustomize hashing ConfigMap names after
all transformers have run).

```yaml
apiVersion: krm.kubed.io
kind: Random
metadata:
  name: random-string
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  type: string
  keepers:
  - kind: Deployment
    fieldPath: /spec/template/spec/containers/0/image
  targets:
  - kind: Job
    fieldPath: /metadata/name
    options:
      delimiter: '-'
      index: 2
```

See [`examples/random`](examples/random/) and
[`docs/transformers/random.md`](docs/transformers/random.md).
