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
| `keepers`         | `[]`        | target selectors with `fieldPath` to seed the RNG      |
| `targets`         | `[]`        | target selectors with `fieldPath` and optional `options` |

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
