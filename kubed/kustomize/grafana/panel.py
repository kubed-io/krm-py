"""Panel: a v2 panel that becomes a resolved local Panel or a GrafanaLibraryPanel.

Listed under generators: it sees no other resources, so only Embed nodes resolve.
Listed under transformers: Target nodes select from the resource list too.
"""
import copy
from kubed.kustomize.grafana import convert, crs, nodes

KRM_ONLY = ("library", "instanceSelector", "allowCrossNamespaceImport")


def transform(krm: dict) -> dict:
  konfig = krm["functionConfig"]
  name = konfig["metadata"]["name"]
  items = [i for i in krm["items"] if not _is_self(i, konfig)]
  spec = nodes.resolve(copy.deepcopy(konfig["spec"]), nodes.base_of(konfig), items)
  v2 = {k: v for k, v in spec.items() if k not in KRM_ONLY}
  if "library" in spec:
    lib = spec.get("library") or {}
    out = crs.library_panel_cr(konfig, convert.to_v1(v2, name), name, lib.get("name", v2.get("title", name)),
                               lib.get("folder"))
  else:
    out = _local(konfig, v2)
  krm["items"] = items + [out]
  return krm


def _is_self(item, konfig):
  """Generator mode hands the function its own config as an item."""
  return (item.get("apiVersion"), item.get("kind"), item.get("metadata", {}).get("name")) == (
    konfig["apiVersion"], konfig["kind"], konfig["metadata"]["name"])


def _local(konfig, spec):
  m = konfig["metadata"]
  meta = {"name": m["name"]}
  if m.get("namespace"):
    meta["namespace"] = m["namespace"]
  if m.get("labels"):
    meta["labels"] = dict(m["labels"])
  meta["annotations"] = {crs.LOCAL: "true", crs.RESOLVED: "true"}
  return {"apiVersion": konfig["apiVersion"], "kind": "Panel", "metadata": meta, "spec": spec}
