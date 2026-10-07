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
  # explicit fieldPaths on the keeper
  - kind: Deployment
    fieldPaths:
    - /spec/template/spec/containers/0/image
  # inverted control: matched resources declare their own keeper paths via
  # `random.krm.kubed.io/keepers.fieldpaths`. Random falls back to the
  # annotation when the keeper has no explicit fieldPaths.
  - kind: ExternalSecret
    matchLabels:
      app: drupal
  # no fieldPaths and no annotation -> whole resource (annotations stripped)
  - kind: ConfigMap
    name: site-.*
  targets:
  - kind: Job
    fieldPath: /metadata/name
    options:
      delimiter: '-'
      index: 2
```

See [`examples/random`](examples/random/) and
[`docs/transformers/random.md`](docs/transformers/random.md).

## Grafana

Panels, dashboards and folders as kustomize resources (`grafana.krm.kubed.io`), deployed
through grafana-operator. Panels and dashboards are plain v2 data; one `GrafanaLibrary`
transformer selects which become library panels and dashboards, in its folder. `Embed`
pulls files in and `Target` pulls resources from the list. See [`examples/grafana`](examples/grafana/) and
[`docs/generators/grafana.md`](docs/generators/grafana.md).
