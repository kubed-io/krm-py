# Grafana KRM: dashboards, panels and folders as kustomize resources

Date: 2026-10-07. Status: implemented on the `grafana` branch; the Redis deploy waits for Dr K.
This spec is deleted by the PR that completes this work; anything lasting moves to the docs.

## Problem

The homelab's Grafana dashboards are built by hand through the Grafana MCP and by ad-hoc
Python generators (`kubed-io/grafana/scripts`, `~/.config/claude/dashboard-gen`). None of
the ~30 code-built dashboards are in git. They are `dashboard.grafana.app` v2 documents of
40–200 KB, and an agent editing one has to hold the whole document at once.

Dashboards should live in git beside the apps they describe, built with kustomize like
everything else, and deployed by GitOps (`kubectl up` from GitHub Actions on the
self-hosted `krm` runner). The source an agent edits should be small YAML files, not one
large JSON document.

## Decisions

Each line was decided by Dr K during brainstorming on 2026-10-07.

| # | Decision |
|---|---|
| D1 | Deploy through grafana-operator v5.25 (already installed). No direct-API deployer. |
| D2 | A dashboard is a small `Dashboard` YAML plus one YAML per panel; files are referenced, not inlined. |
| D3 | Panels are collected from the kustomize ResourceList, not listed by path. |
| D4 | One `Panel` kind. A `library` field decides the output: a `GrafanaLibraryPanel` (applied) or a resolved `Panel` marked `local-config` (embedded by dashboards, never applied). |
| D5 | The `Panel` spec is always the v2 panel element spec. Library panels are converted to the v1 panel model, the only format Grafana 13.2.1 stores them in. |
| D6 | `DataQuery` is data, not a function. It is a local-config resource in the list, or a file. |
| D7 | Every function is its own kind and its own function config: `Panel`, `Dashboard`, `Folder`. |
| D8 | `Panel` runs as a generator (file references only) or as a transformer (file and list references). `Dashboard` and `Folder` run as transformers. |
| D9 | Two client-side node kinds may appear anywhere inside a spec tree: `Embed` (load a file) and `Target` (select from the list). The functions resolve the kinds they recognise and pass everything else through. |
| D10 | `Folder` is a kind. It selects its contents. Folders nest. An explicit folder uid on an object always wins. |
| D11 | The functions set the uid of every Grafana object they create to its `metadata.name`. Authors never write uids. |
| D12 | `Dashboard` exposes the operator's `spec.patch` as a pass-through. Nothing uses it yet. |
| D13 | No templating and no ConfigMap-driven variables. |
| D14 | Repo directories do not decide Grafana folders. |
| D15 | Migration of existing dashboards is out of scope. The first consumer is the Redis dashboard; a skill comes after. |

## Facts this design rests on

Verified against the live cluster and source on 2026-10-07.

- `GrafanaDashboard` only handles v1 dashboards: it POSTs to `/api/dashboards/db`.
  `GrafanaManifest` (operator ≥ v5.22) applies any app-platform resource from
  `spec.template`, which is how a v2 dashboard is deployed. On every resync it GETs the
  live object and PUTs the whole template, with no change check. The default resync is
  10m, and edits made in the UI are reverted.
- Grafana 13.2.1 serves `dashboard.grafana.app` `v2` (preferred), `v2beta1`, `v2alpha1`,
  `v1`, `v1beta1` and `v0alpha1`. It does not serve a `librarypanels` resource;
  grafana/grafana#110230 is migrating library panels to the app platform but has not
  shipped. Library panels exist only behind `/api/library-elements`, in the v1 panel
  model. `GrafanaLibraryPanel` writes them there and updates only when its content hash
  changes. Its uid is `spec.uid`, then the model's `uid`, then the CR's `metadata.uid`;
  its name is the model's `name`. Deleting one fails while dashboards still use it.
- A `GrafanaFolder` with no `spec.uid` gets the CR's `metadata.uid` as its uid. That uid
  is random and unknown at build time. `GrafanaManifest` can only place a dashboard by the
  `grafana.app/folder: <uid>` template annotation, which is the reason for D11.
- Grafana converts its own v2 dashboards to v1 on request:
  `GET /apis/dashboard.grafana.app/v1/.../redis` returns `status.conversion.storedVersion:
  v2` and real v1 panels. Those two renderings are the test fixtures for the v2→v1 panel
  conversion.
- Kustomize behaviour, measured with throwaway builds:
  - A function under `generators:` receives only its own config, never other resources.
  - A function under `transformers:` receives every resource, including `local-config`
    ones, and kustomize drops `local-config` resources from the final output.
  - Built-in `patches:` run after generators and before custom transformers, so a JSON6902
    patch reaches a generated panel. A panel made by a transformer can only be patched
    from an overlay.
  - Functions run with the kustomization directory as their working directory.
  - A resource's source file is known only through `config.kubernetes.io/origin`, which
    kustomize adds when the kustomization sets `buildMetadata: [originAnnotations]`. The
    path is relative to the kustomization directory.
  - The kustomization's `namespace:` reaches generator output but not transformer output.
  - 30 generator runs finish in under a second; importing `kubed.krm.common` costs about
    0.1 s per run.
- A 200 KB custom resource is fine for etcd. Client-side `kubectl apply` copies the
  object into `last-applied-configuration`, and annotations are capped at 256 KiB, so any
  kustomization emitting dashboards must set `kubectl.kubernetes.io/server-side: "true"`,
  which `kubectl up` already honours.

## Kinds

All authoring kinds are `apiVersion: grafana.krm.kubed.io/v1alpha1`, registered as
entry points in the `grafana.krm.kubed.io` group (`load_function` takes the group from
`apiVersion` and the entry-point key from the lower-cased `kind`).

| Kind | Role | Where it goes in a kustomization |
|---|---|---|
| `DataQuery` | a reusable v2 query; data only | `resources:` (with `local-config`), or a file an `Embed` points at |
| `Panel` | a v2 panel; becomes a resolved local `Panel` or a `GrafanaLibraryPanel` | `generators:` or `transformers:` |
| `Dashboard` | a v2 dashboard; becomes a `GrafanaManifest` | `transformers:`, after every Panel transformer |
| `Folder` | a Grafana folder; becomes a `GrafanaFolder` and places its contents | `transformers:`, after `Dashboard` |
| `Embed` | node kind: replaced by a file's contents | anywhere inside a spec |
| `Target` | node kind: replaced by resources selected from the list | anywhere inside a spec |

The layout objects (`GridLayout`, `AutoGridLayout`, `RowsLayout`, `TabsLayout` and their
items `GridLayoutItem`, `AutoGridLayoutItem`, `RowsLayoutRow`, `TabsLayoutTab`) need no
kind of their own. Adding `apiVersion` and `metadata` to any v2 object makes it a
resource a `Target` can select. Any file an `Embed` loads can hold the same shape.

### KRM shape of a v2 object

A v2 object (`{kind, spec}`, or `DataQuery`'s `{kind, group, version, datasource, spec}`)
becomes a resource by adding `apiVersion: grafana.krm.kubed.io/v1alpha1` and `metadata`.
Resolving a resource back into the tree removes exactly those two fields and keeps
`kind`:

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: DataQuery
metadata:
  name: memory-working-set
  labels:
    app: redis
  annotations:
    config.kubernetes.io/local-config: "true"
group: prometheus
version: v0
datasource:
  name: '15f53a2f-8f5b-4047-8c8c-d7fa81ad272d'
spec:
  expr: |-
    sum(container_memory_working_set_bytes{namespace="data", pod=~"redis-.*", container="redis"})
  legendFormat: working set
```

## Node resolution

`resolve(tree, base, items)` walks any value depth-first. Each dict whose `kind` is
`Embed` or `Target` is replaced by what it resolves to, and the result is walked again.
Every function runs this on its own spec before doing anything else.

### `Embed`

```yaml
content:
  kind: Embed
  spec:
    file: masthead.html
```

| Field | Meaning |
|---|---|
| `file` | path relative to `base`, an `http(s)` URL, or a glob (`queries/*.yaml`) |
| `fileType` | `yaml`, `json` or `na`; inferred from the extension as `files.discover_file_type` does |
| `nested` | default true for `yaml`/`json` files (the contents become an object); `false` keeps the raw text |
| `parse` | `json` or `yaml`: parse the file, then serialise it to that format as a string (the existing Embed's `parse`) |

- A non-YAML/JSON file always resolves to a string, so `Embed` can fill string fields such as Business Text's `content`, `helpers`, `afterRender` and `styles`.
- A YAML file with several documents, or a glob, yields several values:
  - in a list position (the parent is a list), the node is replaced by all of them, globs sorted by path and documents in file order;
  - anywhere else, exactly one value must result.
- A loaded object whose `apiVersion` starts with `grafana.krm.kubed.io/` has `apiVersion` and `metadata` removed.
- Nested nodes inside a loaded file resolve with `base` set to that file's directory.
- A cycle (a file reaching itself through nested `Embed`s) is an error.

### `Target`

```yaml
layout:
  kind: Target
  spec:
    kind: RowsLayout
    name: redis-tabs$
```

- `spec` is exactly the selector that `kubed.krm.common.targeted()` already accepts: `apiVersion`, `kind`, `name`, `matchLabels`, `matchAnnotations`. The strings are regular expressions anchored at the start only (`re.match`), so `name: cpu` also matches `cpu-total`; write `cpu$` for an exact match.
- Candidates are the ResourceList items. A matched resource is deep-copied, has `apiVersion` and `metadata` removed, and has its own nodes resolved with `base` set to the directory of that resource's origin path.
- In a list position, the node is replaced by every match, sorted by `metadata.name`. Anywhere else, exactly one match is required.
- Zero matches is always an error. A `Target` in a `Panel` running as a generator therefore always fails, with a message saying that list references need the Panel under `transformers:`.

### `base`

- **A function's own spec:** the directory of its function config's origin path.
- **A list resource:** the directory of that resource's origin path.
- **Nested nodes inside an embedded file:** that file's directory.
- **No origin annotation:** the kustomization directory, which is the working directory.
- **An origin that names a `repo`** (a remote base): an `Embed` there is an error.

### Queries in a panel

- **A `PanelQuery` keeps its per-panel fields.** `refId` and `hidden` stay on the `PanelQuery`; its `query` may be an `Embed` or `Target` that resolves to one `DataQuery`.
- **A node directly in `data.spec.queries` that resolves to `DataQuery` objects** is wrapped into one `PanelQuery` per object, with `refId` set to the object's `metadata.name` and `hidden: false`.
  - This is how one selector pulls in several queries.
  - The resource's metadata is still available because wrapping happens before it is removed.
  - For a file without metadata, `refId` is the file's stem.

## `Panel`

> **Superseded by Round 3:** the `GrafanaLibrary` function replaces this. Kept for the record until this spec is deleted.

Input:

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: Panel
metadata:
  name: redis-memory
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  title: Memory
  description: Memory in use, against the two ceilings that matter.
  data:
    kind: QueryGroup
    spec:
      queries:
      - kind: Target
        spec:
          kind: DataQuery
          matchLabels:
            panel: redis-memory
  vizConfig:
    kind: VizConfig
    group: timeseries
    spec:
      fieldConfig:
        defaults:
          unit: bytes
      options: {}
```

`spec` is a v2 panel element spec (`title`, `description`, `links`, `transparent`,
`data`, `vizConfig`, optionally `id`) plus these KRM-only fields, which are removed from
every output:

| Field | Meaning |
|---|---|
| `library` | present (even `{}`) makes this a library panel |
| `library.name` | library panel name; default `spec.title` |
| `library.folder` | uid of the folder to place it in; explicit, so it beats any `Folder` |
| `instanceSelector` | default `matchLabels: {app.kubernetes.io/name: grafana}` |
| `allowCrossNamespaceImport` | default `true` |

The function resolves nodes, removes its own config from `items` if kustomize passed it
there (generator mode does), then appends one output. In transformer mode every other
item passes through unchanged.

- **Without `library`, the output is a resolved local Panel:**
  - kind `Panel`, same name, labels copied, the resolved spec with the KRM-only fields removed;
  - annotations `config.kubernetes.io/local-config: "true"` and `grafana.krm.kubed.io/resolved: "true"`;
  - no function annotation.
- **With `library`, the output is a `GrafanaLibraryPanel`:**
  - `metadata.name` and `spec.uid` are the Panel's `metadata.name` (D11);
  - `spec.json` is the v1 model as compact JSON, with `uid` and `name` set inside it;
  - `spec.folderUID` is set from `library.folder` when given;
  - `instanceSelector` and `allowCrossNamespaceImport` are set from the defaults;
  - labels are copied, and the annotation `grafana.krm.kubed.io/kind: Panel` is added.

### v2 panel element → v1 panel model

The rules reproduce Grafana's own conversion, as observed on the Redis dashboard (its v2
and v1 renderings, 2026-10-07). They are checked panel by panel against the fixtures.

| v1 field | From | Omitted when |
|---|---|---|
| `type` | `vizConfig.group` | never |
| `pluginVersion` | `vizConfig.version`, even when it is `""` | the key is absent |
| `title` | `title` | never (an empty title stays `""`) |
| `description` | `description` | empty |
| `links` | `links` | empty |
| `transparent` | `transparent` | false or unset |
| `fieldConfig` | `vizConfig.spec.fieldConfig`, without an empty `defaults` or `overrides` | both empty |
| `options` | `vizConfig.spec.options` | not set |
| `targets` | one per `PanelQuery`: `{datasource: {type: query.group, uid: query.datasource.name}, **query.spec, refId}`, plus `hide: true` only when the `PanelQuery` is hidden (the Redis fixtures have no hidden query, so this one rule is from the v1 schema, not observed) | never (`[]` when there are no queries) |
| `datasource` | the shared `{type, uid}` when every target has the same one | no queries, or mixed datasources |
| `transformations` | one per `{kind: Transformation, group, spec}`: `{id: group, **spec}` | empty |
| `maxDataPoints`, `interval`, `timeFrom`, `timeShift`, `cacheTimeout`, `queryCachingTTL`, `hideTimeOverride` | `data.spec.queryOptions` | not set |

`id` and `gridPos` are layout concerns. They are not part of a library panel model, and
the fixture comparison removes them from Grafana's v1 panels.

## `Dashboard`

> **Superseded by Round 3:** the `GrafanaLibrary` function replaces this. Kept for the record until this spec is deleted.

Input:

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: Dashboard
metadata:
  name: redis
  namespace: observe
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  folder: cfyzcbzldfg1sa
  title: Redis
  elements:
    app-masthead:
      kind: LibraryPanel
      spec:
        id: 1
        title: App masthead
        libraryPanel:
          uid: app-masthead
          name: App masthead
  layout:
    kind: RowsLayout
    spec:
      rows:
      - kind: Embed
        spec:
          file: rows/overview.yaml
```

`spec` is a v2 dashboard spec plus these KRM-only fields:

| Field | Meaning |
|---|---|
| `folder` | uid of an existing folder; explicit, so it beats any `Folder` |
| `instanceSelector`, `allowCrossNamespaceImport` | same defaults as Panel |
| `resyncPeriod` | default `24h`; a CR change still reconciles immediately |
| `suspend` | pass-through to the GrafanaManifest |
| `patch` | pass-through to `GrafanaManifest.spec.patch` (D12) |

Steps:

1. Resolve nodes in `spec`.
2. Walk `layout` and collect every `ElementReference` name, in order of first appearance.
3. Fill in `elements`:
   - **Explicit entries** already in `elements` are kept as written. This is how a dashboard uses a library panel that is not managed in git.
   - **Any other referenced name** is looked up among the items:
     - a resolved local `Panel` with that name is embedded as `{kind: Panel, spec: <its spec>}`;
     - a `GrafanaLibraryPanel` with that name becomes `{kind: LibraryPanel, spec: {id, title, libraryPanel: {uid: <spec.uid>, name: <model name>}}}`.
   - **A name that matches nothing** is an error.
4. Give every element without an `id` the lowest positive integer not yet used, in reference order.
5. Leave the resolved local `Panel`s in `items`. Another dashboard may embed the same panel, and kustomize drops them from the output because they are `local-config`.
6. Append a `GrafanaManifest`:

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaManifest
metadata:
  name: redis
  namespace: observe
  labels: {}
  annotations:
    grafana.krm.kubed.io/kind: Dashboard
spec:
  instanceSelector:
    matchLabels:
      app.kubernetes.io/name: grafana
  allowCrossNamespaceImport: true
  resyncPeriod: 24h
  template:
    apiVersion: dashboard.grafana.app/v2
    kind: Dashboard
    metadata:
      name: redis
      annotations:
        grafana.app/folder: cfyzcbzldfg1sa
    spec: {}
```

- The template's `metadata.name` (the dashboard uid) is the `Dashboard`'s `metadata.name` (D11).
- `metadata.namespace` is copied from the `Dashboard` config when set, because transformer output does not receive the kustomization's `namespace:`. The same holds for a `Panel` or `Folder` run as a transformer, and for the kustomization's `labels:`.
- The `grafana.app/folder` annotation is written only when a folder is known.

## `Folder`

> **Superseded by Round 3:** the `GrafanaLibrary` function replaces this. Kept for the record until this spec is deleted.

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: Folder
metadata:
  name: apps
  namespace: observe
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  title: apps
  target:
    matchLabels:
      grafana.kubed.io/folder: apps
```

| Field | Meaning |
|---|---|
| `title` | folder title; default `metadata.name` |
| `folder` | uid of an existing parent folder; explicit, so it beats any parent `Folder` |
| `target` | a `targeted()` selector over the objects to place in this folder |
| `permissions` | pass-through to `GrafanaFolder.spec.permissions` |
| `instanceSelector`, `allowCrossNamespaceImport` | same defaults as Panel |

Steps:

1. Append a `GrafanaFolder` with `metadata.name` and `spec.uid` set to the `Folder`'s name (D11), plus `title`, `parentFolderUID` (from `folder`) and the defaults.
2. Match `target` against every output object that carries `grafana.krm.kubed.io/kind`. Each object is matched as if its `kind` were the authoring kind in that annotation, so `kind: Dashboard` selects the `GrafanaManifest` built from a `Dashboard`.
3. Place each match:
   - **`GrafanaManifest`:** set the template annotation `grafana.app/folder`.
   - **`GrafanaLibraryPanel`:** set `spec.folderUID`.
   - **`GrafanaFolder`:** set `spec.parentFolderUID`.
4. If a match already has a folder (set explicitly, or by an earlier `Folder`), leave it and add a warning result naming both folders.

Folders nest by selecting other folders: a parent `Folder` listed after its children
places them.

## Round 2: variables

Decided by Dr K on 2026-10-07, after the Redis dashboard built.

**Requirements:**
- **An `Embed` in `variables` adds variables from a file.** A multi-document YAML file (documents separated by `---`) adds one variable per document, in file order. A single-document file adds one.
- **A `Target` in `variables` adds every matching variable resource from the list,** or exactly one when its selector names one.
- **A `QueryVariable`'s `spec.query` resolves too:** it may be an `Embed` or a `Target` that comes out as one `DataQuery`, the same as a panel query.
- **Every v2 variable kind works this way** (`QueryVariable`, `ConstantVariable`, `CustomVariable`, `TextVariable`, `IntervalVariable`, `DatasourceVariable` and the rest), because resolution never inspects the kind.

**Design.** No new mechanism is needed: node resolution already expands nodes in list positions and resolves them in single positions. This round makes variables an explicit, tested contract.
- **A variable as a resource** is a v2 variable plus `apiVersion: grafana.krm.kubed.io/v1alpha1` and `metadata`. Listed under `resources:` it needs `config.kubernetes.io/local-config: "true"`. In a file that an `Embed` loads, it needs neither.

  ```yaml
  apiVersion: grafana.krm.kubed.io/v1alpha1
  kind: ConstantVariable
  metadata:
    name: redis-k8s-selector
    labels:
      dashboard: redis
    annotations:
      config.kubernetes.io/local-config: "true"
  spec:
    name: k8s_selector
    query: app.kubernetes.io/name=redis
    hide: hideVariable
  ```

- **Order matters.** Grafana shows variables in list order, and a query variable can only use variables listed before it. An `Embed` keeps file order. A `Target` sorts by `metadata.name`, as everywhere else. When order matters, use an `Embed`, or name the resources so they sort into the order wanted.
- **`Dashboard` runs as a transformer,** so its `Target`s always see the list.

**Acceptance:**
1. **Tests** cover: a multi-document file embedded into `variables`; a single-document one; a `Target` adding several variables and one adding one; and a `QueryVariable` whose `spec.query` is an `Embed` and one whose `spec.query` is a `Target`.
2. **The example** (`examples/grafana`) uses both a variables file and listed variable resources.
3. **The Redis dashboard's 19 variables move to `grafana/variables.yaml`,** embedded from `dashboard.yaml`, and the build still matches the live dashboard with zero differences.

## Round 3: one function, `GrafanaLibrary`

Decided by Dr K on 2026-10-07, once Redis was built from sources. This supersedes the
`Panel`, `Dashboard` and `Folder` functions (D4, D7, D8 and D10). There is no backward
compatibility, because this has a single user: those three entry points are removed.

| # | Decision |
|---|---|
| R1 | One KRM function, `GrafanaLibrary`, listed under `transformers:`. It is the only resource with a function annotation. |
| R2 | Every other `grafana.krm.kubed.io` kind is plain data under `resources:`: `Panel`, `Dashboard`, `DataQuery`, the variable kinds and the layout kinds. They mirror Grafana's kinds and add `Embed` and `Target`. |
| R3 | The library's `panels` selector chooses the Panels that become library panels. Its `dashboards` selector chooses the Dashboards it builds. Both are `targeted()` selectors, so the author picks the label that admits a resource. |
| R4 | Only resources whose `apiVersion` is `grafana.krm.kubed.io/...` are candidates. Operator kinds already in the list (a `GrafanaDashboard`, say) are finished and ignored. |
| R5 | The library has one folder. `spec.folder.uid` names an existing folder; `spec.folder.title` (and an optional `parent`) makes the library create a `GrafanaFolder`. Everything it emits goes in that folder, so placement never conflicts. |
| R6 | The library marks everything it used `config.kubernetes.io/local-config: "true"` and leaves it in the list; kustomize drops it. Nothing is pruned. |
| R7 | A resource of ours that no library used keeps no `local-config`. It reaches the output, and `kubectl plan`/`up` fails on it because the cluster has no such kind. That failure is the guard. The function itself does not fail, because a later library in the same kustomization may still use the resource. |
| R8 | One library emits many library panels and many dashboards. |

### Shape

```yaml
apiVersion: grafana.krm.kubed.io/v1alpha1
kind: GrafanaLibrary
metadata:
  name: redis
  namespace: observe
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: kubectl-kubed
spec:
  folder:
    uid: cfyzcbzldfg1sa
  panels:
    matchLabels:
      grafana.kubed.io/library-panel: redis
  dashboards:
    matchLabels:
      grafana.kubed.io/dashboard: redis
```

| Field | Meaning |
|---|---|
| `folder.uid` | an existing folder uid. With `title`, it is the uid of the folder the library creates. |
| `folder.title` | create a `GrafanaFolder` with this title. Its uid is `folder.uid`, or else the library's `metadata.name`. |
| `folder.parent` | the parent folder uid of a created folder |
| `panels` | a selector for the `Panel`s that become library panels. `kind: Panel` is implied. Omitted, there are none. |
| `dashboards` | a selector for the `Dashboard`s to build. `kind: Dashboard` is implied. Omitted, there are none. |
| `instanceSelector`, `allowCrossNamespaceImport`, `resyncPeriod` | defaults for everything the library emits (`matchLabels: {app.kubernetes.io/name: grafana}`, `true`, `24h`) |

### The data kinds

- **`Panel`:** `spec` is a v2 panel element spec. There is no `library` field, because the library's selector decides.
  - The library panel's uid is `metadata.name`.
  - Its name is `spec.title`, or `metadata.name` when the title is empty. The annotation `grafana.krm.kubed.io/library-name` overrides it.
- **`Dashboard`:** `spec` is a v2 dashboard spec, with optional explicit `elements`. There is no `folder` field, because the library places it. `resyncPeriod`, `suspend` and `patch` are optional per-dashboard overrides, removed from the spec and passed to its `GrafanaManifest`.
- **`DataQuery`, variable and layout kinds:** reached by `Target` or `Embed`, exactly as before.

### What the library does

1. **Candidates** are the items whose `apiVersion` starts with `grafana.krm.kubed.io/`.
2. **Library panels.** For each `Panel` the `panels` selector matches:
   - resolve its nodes, with `base` set to its origin directory;
   - convert it to the v1 model;
   - emit a `GrafanaLibraryPanel` in the library's folder.
3. **Dashboards.** For each `Dashboard` the `dashboards` selector matches, resolve its nodes, then fill `elements` by `ElementReference` name. The first match wins:
   1. an explicit entry;
   2. a library panel, either this library's or a `GrafanaLibraryPanel` already in the list (from an earlier library), becomes a `LibraryPanel` reference;
   3. any other `Panel` of ours with that name is resolved and embedded;
   4. otherwise `ElementNotFound`.

   Then emit a `GrafanaManifest` with the folder annotation.
4. **Folder:** with `folder.title`, emit the `GrafanaFolder`.
5. **Mark as used:** add `local-config` to every resource of ours the library used. That means the selected panels and dashboards, the embedded panels, and every resource a `Target` matched while resolving.
6. **Output metadata:** outputs take the library's `metadata.namespace`, because transformer output does not receive the kustomization's `namespace:`. They keep their source's labels and carry `grafana.krm.kubed.io/kind`.

Transformers run in order, so a library listed later can reference an earlier library's panels by name.

### In a kustomization

```yaml
buildMetadata:
- originAnnotations
resources:
- panels/
- variables/
- dashboard.yaml
transformers:
- library.yaml
```

### Acceptance

1. **The function and its tests.** `GrafanaLibrary` is the only `grafana.krm.kubed.io` entry point, and the `Panel`, `Dashboard` and `Folder` modules and entry points are gone. Tests cover:
   - panel and dashboard selection;
   - only our apiVersion being a candidate;
   - an existing folder versus a created one;
   - library versus embedded panels;
   - an earlier library's panels referenced by name;
   - `local-config` added to everything used;
   - an unused resource left unmarked.
2. **The example** uses one library.
3. **Redis:**
   - panels and the dashboard are plain resources plus one `library.yaml`;
   - `variables/kustomization.yaml` no longer needs `commonAnnotations`, because the library marks what its `Target` uses;
   - the build matches the live dashboard, apart from the description's trailing space.

## Using it in a kustomization

> **Superseded by Round 3:** the `GrafanaLibrary` function replaces this. Kept for the record until this spec is deleted.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
metadata:
  name: grafana-redis-provider
  annotations:
    kubectl.kubernetes.io/server-side: "true"
namespace: observe
buildMetadata:
- originAnnotations
resources:
- queries/
generators:
- panels/memory.yaml
- panels/clients.yaml
transformers:
- dashboard.yaml
```

- `buildMetadata: [originAnnotations]` is required whenever a relative `Embed` is used outside the kustomization directory, and recommended always.
- `kubectl.kubernetes.io/server-side: "true"` is required in any kustomization that emits dashboards.
- `transformers:` run in the order listed: Panel transformers, then `Dashboard`, then `Folder`.
- Removing a library `Panel` from git prunes its `GrafanaLibraryPanel`. The operator then refuses to delete the library panel from Grafana while dashboards still use it.

## Errors

Every failure raises a `KubedError` subclass, which the executor prints verbatim:

| Error | Message names |
|---|---|
| `EmbedError` | the file, the base it was resolved against, and why (missing, cycle, remote base, wrong count) |
| `TargetError` | the selector, the number of matches, and the position (list or single) |
| `ElementNotFound` | the dashboard, the element name, and the Panel/library names that do exist |
| `ConversionError` | the panel and the v2 field that has no v1 mapping |

## Testing

- **Unit tests in `tests/`, run with pytest:**
  - node resolution (`Embed` text, nested and glob; `Target` single and list; cycles; errors);
  - the v2→v1 conversion, checked against every Redis panel in the fixtures;
  - Panel, Dashboard and Folder outputs, built from small in-memory ResourceLists.
- **Fixtures:**
  - `tests/fixtures/grafana/redis.v2.json` and `redis.v1.json`, captured from the live Grafana on 2026-10-07 with the Grafana MCP;
  - small YAML trees under `examples/grafana/`.
- **Build test:** `kustomize build examples/grafana --enable-alpha-plugins --enable-exec` with the editable install on the `PATH`; the result is diffed against a committed expected output.
- **End to end:** the Redis dashboard, below.
- **Version churn:** after deployment, `dashboard.grafana.app` version history is compared across two resyncs. If unchanged PUTs add versions, the `24h` default stays; otherwise it may be relaxed.

## First consumer: the Redis dashboard

Redis (`uid: redis`, folder `apps`, 42 KB) is the smallest app dashboard that uses every
feature: rows, grids and tabs; 18 variables (one query, 17 constants that feed library
panels); 13 library panels shared with every app dashboard; and 13 panels of its own.

- **Where the sources live:** `kubed-io/redis/grafana/`, its own kustomization (`kubectl.kubernetes.io/server-side: "true"`, namespace `observe`), deployed with `kubectl up grafana`.
- **Panels:** each of Redis's own 13 panels becomes a `Panel` and keeps its live `id`. Long Business Text or text strings move to sibling files through `Embed`.
- **The 13 shared library panels stay explicit `elements` entries.** They are not in git yet, and moving them belongs to the grafana repo, not this work.
- **Porting may be scripted.** A one-off script that splits the live v2 document into sources belongs in `stuff/` and is not committed.

Acceptance:
1. **The build matches the live dashboard.** With element keys mapped to panel ids on both sides, the built `GrafanaManifest` template spec equals the live v2 spec. A remaining difference is either a function bug, fixed in krm-py with a test that reproduces it, or a field Grafana fills in on save, which is reported to Dr K.
2. **`kubectl plan grafana` shows only the new `GrafanaManifest`.** Dr K approves before `kubectl up`.
3. **After `kubectl up`, the dashboard matches and renders.**
   - The `GrafanaManifest` status reports a successful apply to `observe/grafana`.
   - The live dashboard still matches the build.
   - Exactly one new dashboard version exists.
   - The dashboard renders every row and tab with no missing library panel or plugin; checked in a browser with selenium-flow.
4. **Version churn is measured and recorded.** A temporary short `resyncPeriod` shows whether an unchanged PUT adds a version. The answer goes into this spec's "Facts" section.

## Rollout

Each step is outward-facing and waits for Dr K's yes:

1. **The krm-py PR:** one PR from the `grafana` branch.
2. **The release:** tag the next kubed-krm version after merge; `publish.yml` publishes to PyPI on the tag.
3. **The runner:** bump `KUBED_KRM_VERSION` in `kubed-io/github/runners/krm/Dockerfile` (0.0.6 today).
4. **GitOps:** a workflow in `kubed-io/redis` that runs `kubectl up grafana` on the `krm` runner when `grafana/**` changes on `main`. It authenticates the way `deploy.yml` does today (kluster-konnect).

## Notes for the implementer

Facts about this environment, found while writing this spec:

- **The pod has no pytest.** Install the test dependencies with `pip install --target` into `stuff/` (globally gitignored) and run with `PYTHONPATH=.:<that dir>`. The existing suite passed 5/5 that way on 2026-10-07.
- **The globally installed `kubectl-kubed` is kubed-krm 0.0.5.** For kustomize to run the checkout, put a small wrapper named `kubectl-kubed` first on `PATH` that runs `kubed.krm.common.execute()` with the checkout on `PYTHONPATH`. This was verified with `examples/random`.
- **New entry points need fresh package metadata.** `load_function` finds functions through entry points, which come from the gitignored `kubed_krm.egg-info/`. Regenerate it with setuptools' `egg_info`; that needs `setuptools` and `setuptools_scm` in the scratch install.
- **Sphinx would pick up `docs/superpowers/`.** Add it to `exclude_patterns` in `docs/conf.py`.
- **Fixtures can be fetched as Grafana's service account.** `kubed-io/grafana/scripts/grafana.py` reads the token with `op read`, and the Grafana MCP can do the same GETs.

## Out of scope

- Migrating the other dashboards. A skill that teaches agents this format comes after the Redis dashboard works.
- A `kubectl grafana` developer plugin (`check`, `diff`, preview).
- Static assets for panels. They are the `kubed-io/cdn` repo, with its own spec.
- Git Sync. App-platform library panels, when grafana/grafana#110230 ships: only the `GrafanaLibraryPanel` output would change.
