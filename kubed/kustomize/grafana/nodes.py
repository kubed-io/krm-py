"""Client-side node kinds for the grafana.krm.kubed.io functions.

`Embed` (a file) and `Target` (resources from the list) may sit anywhere in a spec
tree. resolve() replaces each with what it points at and passes everything else
through, so a spec is plain v2 once it has run.
"""
import copy
import glob
import json
import os
import yaml
from kubed.krm import common as c, files as f
from kubed.krm.errors import EmbedError, TargetError

GROUP = "grafana.krm.kubed.io/"
ORIGIN = "config.kubernetes.io/origin"
NODES = ("Embed", "Target")


def base_of(res: dict):
  """The directory relative Embed paths inside res resolve against.

  "." (the kustomization directory) without an origin annotation, and None for a
  resource from a remote base, where Embed is refused.
  """
  origin = res.get("metadata", {}).get("annotations", {}).get(ORIGIN)
  if not origin:
    return "."
  o = yaml.safe_load(origin)
  if o.get("repo"):
    return None
  return os.path.dirname(o.get("path", "")) or "."


def strip(obj):
  """A v2 object wrapped as a grafana.krm.kubed.io resource, back to plain v2."""
  if isinstance(obj, dict) and str(obj.get("apiVersion", "")).startswith(GROUP):
    return {k: v for k, v in obj.items() if k not in ("apiVersion", "metadata")}
  return obj


def is_node(v) -> bool:
  return isinstance(v, dict) and v.get("kind") in NODES and isinstance(v.get("spec"), dict)


def resolve(value, base=".", items=None, key=None, seen=frozenset(), used=None):
  """Replace every Embed and Target node in value.

  Args:
    value: any spec tree.
    base: the directory relative Embed paths resolve against; None inside a remote base.
    items: the ResourceList items a Target selects from.
    key: the dict key value sits under; nodes directly in `queries` wrap DataQuery results, and
      nodes in an `elements` map spread into it, each value keyed by its metadata name.
    seen: files and resources already being resolved, to catch cycles.
    used: when given, collects (kind, name) of every resource a Target matched.

  Returns:
    value with every node replaced.
  """
  if isinstance(value, list):
    out = []
    for v in value:
      if is_node(v):
        out.extend(_wrap(n, o) if key == "queries" else o for n, o in _load(v, base, items, seen, True, used))
      else:
        out.append(resolve(v, base, items, None, seen, used))
    return out
  if isinstance(value, dict):
    if is_node(value):
      return _load(value, base, items, seen, False, used)[0][1]
    out = {}
    for k, v in value.items():
      if key == "elements" and is_node(v):
        # a node among the elements spreads: each value it brings in is keyed by its own name
        for n, o in _load(v, base, items, seen, True, used):
          if n in out or n in value:
            raise (EmbedError if v["kind"] == "Embed" else TargetError)(f"elements: {n} is defined more than once")
          out[n] = o
      else:
        out[k] = resolve(v, base, items, k, seen, used)
    return out
  return value


def _load(node, base, items, seen, many, used=None):
  """A node's values as (name, value) pairs, each already resolved."""
  spec = node["spec"]
  if node["kind"] == "Embed":
    error, what = EmbedError, "Embed " + str(spec.get("file"))
    found = _embed(spec, base, items, seen, used)
  else:
    error, what = TargetError, "Target " + json.dumps(spec, sort_keys=True)
    found = _target(spec, items, seen, used)
  if not found:
    raise error(f"{what}: resolved to nothing")
  if not many and len(found) != 1:
    raise error(f"{what}: must resolve to exactly one value outside a list, got {len(found)}")
  return found


def _embed(spec, base, items, seen, used=None):
  file = spec["file"]
  if base is None:
    raise EmbedError(f"Embed {file}: not supported inside a remote base")
  if file.startswith("http"):
    paths = [file]
  else:
    path = os.path.normpath(os.path.join(base, file))
    paths = sorted(glob.glob(path)) if glob.has_magic(path) else [path]
  out = []
  for p in paths:
    if p in seen:
      raise EmbedError(f"Embed {file}: cycle through {p}")
    if not p.startswith("http") and not os.path.isfile(p):
      raise EmbedError(f"Embed {file}: {p} does not exist (resolved against {base})")
    text = f.get_file_contents(p)
    text = text.decode() if isinstance(text, bytes) else text
    ftype = spec.get("fileType") or f.discover_file_type(p)
    stem = os.path.splitext(os.path.basename(p))[0]
    if "parse" in spec:
      if ftype not in ("yaml", "json"):
        raise EmbedError(f"Embed {file}: parse needs a yaml or json file, {p} is {ftype}")
      out.append((stem, f.parse_to(f.parse_from(text, ftype), spec["parse"])))
    elif ftype in ("yaml", "json") and spec.get("nested", True):
      docs = [d for d in yaml.safe_load_all(text) if d is not None] if ftype == "yaml" else [json.loads(text)]
      inner = os.path.dirname(p) or "."
      for d in docs:
        name = d.get("metadata", {}).get("name", stem) if isinstance(d, dict) else stem
        out.append((name, resolve(strip(d), inner, items, None, seen | {p}, used)))
    else:
      out.append((stem, text))
  return out


def _target(spec, items, seen, used=None):
  if not items:
    raise TargetError(f"Target {json.dumps(spec, sort_keys=True)}: there is no resource list to select from; "
                      "a Panel needs to be under transformers: for list references")
  out = []
  for m in sorted((i for i in items if c.targeted(i, spec)), key=lambda i: i["metadata"]["name"]):
    ref = f"{m['kind']}/{m['metadata']['name']}"
    if ref in seen:
      raise TargetError(f"Target {json.dumps(spec, sort_keys=True)}: cycle through {ref}")
    if used is not None:
      used.add((m["kind"], m["metadata"]["name"]))
    out.append((m["metadata"]["name"], resolve(strip(copy.deepcopy(m)), base_of(m), items, None, seen | {ref}, used)))
  return out


def _wrap(name, value):
  """A DataQuery directly in a queries list becomes a PanelQuery named after it."""
  if isinstance(value, dict) and value.get("kind") == "DataQuery":
    return {"kind": "PanelQuery", "spec": {"refId": name, "hidden": False, "query": value}}
  return value
