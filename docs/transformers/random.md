# Random Transformer

Generates a random string or number and writes it into one or more target
resource fields. When `keepers` are configured, the output is
deterministically seeded by the values found at those keeper paths — same
inputs, same output — borrowing the semantics of Terraform's
[`random_string`](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string)
resource.

```yaml
apiVersion: krm.kubed.io
kind: Random
```

## Why

Kustomize's ConfigMap/Secret hash suffix is appended *after* every
transformer and generator runs, so you can't copy that final name into
another resource (like a Job). The Random transformer fills the gap: pick
upstream values as keepers, drop the generated token into the names you
care about, and you get a Job name that only changes when the upstream
values change.

## Spec

| Field             | Default     | Notes                                                  |
| ----------------- | ----------- | ------------------------------------------------------ |
| `type`            | `string`    | `string` or `number`                                   |
| `length`          | `8`         | string length                                          |
| `lower`           | `true`      | include `a-z`                                          |
| `upper`           | `true`      | include `A-Z`                                          |
| `numeric`         | `true`      | include `0-9`                                          |
| `special`         | `false`     | include special characters                             |
| `override_special`| punctuation | override the special-character pool                    |
| `min` / `max`     | `0` / `999999` | bounds when `type: number`                          |
| `keepers`         | `[]`        | resource selectors that seed the RNG; `fieldPaths` is optional |
| `targets`         | `[]`        | resource selectors with required `fieldPath` and optional `options` |

### Keeper shapes

Each keeper is a resource selector (`kind`/`name`/`apiVersion`/`matchLabels`/`matchAnnotations`) with an optional `fieldPaths` list. What gets fed into the seed depends on what's listed:

- **One `fieldPaths` entry, scalar value** — used as-is (`/spec/template/spec/containers/0/image`).
- **One `fieldPaths` entry, object value** — JSON-serialized with sorted keys so any nested change re-rolls (`/spec/target/template/data`).
- **One `fieldPaths` entry, large string** — fed in directly; size doesn't matter (`/data/big.yaml` could be many KB).
- **Multiple `fieldPaths` entries** — each path's value is appended to the seed in declared order. Use this to track a handful of specific fields on a resource without going whole-resource.
- **No `fieldPaths`** — see the path-resolution fallback below.

When a selector matches multiple resources, they're sorted by `kind/namespace/name` so the seed doesn't depend on items order.

### Inverted control via annotation

Path resolution is a fallback chain per matched resource:

1. The keeper's own `fieldPaths` if any.
2. Otherwise, the resource's own `random.krm.kubed.io/keepers.fieldpaths` annotation. The value is a newline-separated list of JSON-pointer paths.
3. Otherwise, the entire resource (annotations stripped).

The annotation lets a component opt its own resource into the seed without the `random.yaml` needing to enumerate paths. Drop in an optional component that introduces a new resource, annotate it, and the existing Random transformer picks up its fields automatically:

```yaml
metadata:
  annotations:
    random.krm.kubed.io/keepers.fieldpaths: |
      /spec/data
      /spec/foo/bar
```

`options` on a target:

- `delimiter`: split the existing field value on this character
- `index`: replace the slot at this index with the random value

## Module Def

```{eval-rst}
.. autofunction:: kustomize.random.transform
```

```{eval-rst}
.. autofunction:: kustomize.random.resolve_keepers
```

```{eval-rst}
.. autofunction:: kustomize.random.generate
```

```{eval-rst}
.. autofunction:: kustomize.random.patch_value
```

## Example

```{literalinclude} ../../examples/random/random.yaml
:language: yaml
```
