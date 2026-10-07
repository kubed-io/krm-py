# Grafana

Grafana dashboards, panels and folders as kustomize resources, deployed through
grafana-operator. One function, `GrafanaLibrary`, turns plain `grafana.krm.kubed.io`
data into operator resources.

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: GrafanaLibrary
spec:
  folder:
    uid: apps            # an existing folder; or `title` (+ `parent`) to create one
  panels:                # these Panels become library panels
    matchLabels:
      grafana.kubed.io/library-panel: redis
  dashboards:            # these Dashboards are built
    matchLabels:
      grafana.kubed.io/dashboard: redis
```

List it under `transformers:`. Everything else is data under `resources:`:

| Kind | Is | Becomes |
|---|---|---|
| `Panel` | a v2 panel spec | a `GrafanaLibraryPanel` when the library selects it; otherwise embedded into the dashboards that name it |
| `Dashboard` | a v2 dashboard spec whose layout names panels with `ElementReference` | a `GrafanaManifest` holding a `dashboard.grafana.app/v2` Dashboard, when the library selects it |
| `DataQuery`, variables, layouts | v2 objects with `apiVersion` and `metadata` | pulled in by `Target` |

Anywhere inside a spec, `kind: Embed` (`spec.file`) is replaced by a file's contents and
`kind: Target` (a selector: `kind`, `name`, `matchLabels`) by resources from the list. A
multi-document file or a selector with several matches expands in a list, so variables
can come in groups; a file keeps its order, a `Target` sorts by name.

The library marks everything it used `local-config`, so kustomize drops it. A resource of
ours that no library used stays in the output, and `kubectl up` fails on it.

- Set `buildMetadata: [originAnnotations]`, so `Embed` paths resolve next to the file
  they are written in.
- Set `kubectl.kubernetes.io/server-side: "true"`; dashboards outgrow client-side
  apply's annotation.
- Set `metadata.namespace` on the library; transformer output does not get the
  kustomization's `namespace:`.

## Example

```{literalinclude} ../../examples/grafana/kustomization.yaml
:language: yaml
```
