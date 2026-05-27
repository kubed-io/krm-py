# Random Transformer Example

Shows the `Random` transformer with both explicit fieldPaths and the
inverted-control annotation pattern. Inputs in `some-app.yaml`: a Deployment,
a Job, and two ConfigMaps.

The Job's name suffix is the target — random token goes into the third
slot of `web-migrate-PLACEHOLDER`. The keepers in `random.yaml` exercise
both styles:

- **Explicit fieldPaths** — the Deployment keeper enumerates
  `/spec/template/spec/containers/0/image` on the selector itself.
- **Inverted control via annotation** — the ConfigMap keeper has no
  fieldPaths; each matched ConfigMap declares its own via
  `random.krm.kubed.io/keepers.fieldpaths` in its metadata. Drop in a new
  ConfigMap with the `seeder: keep-me` label and the right annotation,
  and it's part of the seed without editing `random.yaml`.

Bump the image, change any annotated field, or change a ConfigMap's set of
annotated paths — the Job name shifts. Unrelated annotation churn — the
Job name stays put. If a keeper declares explicit `fieldPaths` AND a
matched resource also has the annotation, the explicit paths win and a
`warning` entry is appended to the ResourceList's `results`.
