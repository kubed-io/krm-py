# Grafana

Grafana dashboards, panels and folders as kustomize resources, deployed through
grafana-operator.

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: Panel      # or Dashboard, Folder
```

| Kind | Runs as | Emits |
|---|---|---|
| `Panel` | generator or transformer | a resolved local `Panel`, or a `GrafanaLibraryPanel` when `spec.library` is set |
| `Dashboard` | transformer, after the Panel transformers | a `GrafanaManifest` holding a `dashboard.grafana.app/v2` Dashboard |
| `Folder` | transformer, after Dashboard | a `GrafanaFolder`, and places what its `target` selects |

A `Panel` is a v2 panel spec; a `Dashboard` is a v2 dashboard spec whose layout names
panels with `ElementReference`. Anywhere inside either, `kind: Embed` (`spec.file`) is
replaced by a file's contents and `kind: Target` (a selector: `kind`, `name`,
`matchLabels`) by resources from the list. `DataQuery` resources are plain data that
panels pull in either way.

Variables work the same way. An `Embed` in `variables` adds one variable per YAML
document in the file, in file order; a `Target` adds every matching variable resource,
sorted by name. A `QueryVariable`'s `spec.query` can be an `Embed` or `Target` of a
`DataQuery`. Grafana keeps variables in list order, and a query variable can only use
the ones before it, so reach for a file when order matters.

- Set `buildMetadata: [originAnnotations]`, so `Embed` paths resolve next to the file
  they are written in.
- Set `kubectl.kubernetes.io/server-side: "true"`; dashboards outgrow client-side
  apply's annotation.
- Transformer output does not get the kustomization's `namespace:`. Set
  `metadata.namespace` on any `Panel`, `Dashboard` or `Folder` listed under
  `transformers:`.

## Example

```{literalinclude} ../../examples/grafana/kustomization.yaml
:language: yaml
```
