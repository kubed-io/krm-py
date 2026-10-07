"""Dashboard: a v2 dashboard whose panels are collected from the list, deployed as a GrafanaManifest.

Runs under transformers:, after every Panel transformer, so resolved Panels and
GrafanaLibraryPanels are already in the list.
"""
import copy
import json
from kubed.krm.errors import ElementNotFound
from kubed.kustomize.grafana import crs, nodes

KRM_ONLY = ("folder", "instanceSelector", "allowCrossNamespaceImport", "resyncPeriod", "suspend", "patch")


def transform(krm: dict) -> dict:
  konfig = krm["functionConfig"]
  name = konfig["metadata"]["name"]
  items = krm["items"]
  spec = nodes.resolve(copy.deepcopy(konfig["spec"]), nodes.base_of(konfig), items)
  dash = {k: v for k, v in spec.items() if k not in KRM_ONLY}
  dash["elements"] = elements(name, dash.get("elements", {}), references(dash.get("layout", {})), items)
  krm["items"] = items + [crs.manifest_cr(konfig, dash, spec.get("folder"))]
  return krm


def references(layout) -> list:
  """ElementReference names in the order they first appear."""
  found = []

  def walk(v):
    if isinstance(v, dict):
      if v.get("kind") == "ElementReference" and v.get("name") not in found:
        found.append(v["name"])
      for x in v.values():
        walk(x)
    elif isinstance(v, list):
      for x in v:
        walk(x)

  walk(layout)
  return found


def elements(dashboard: str, explicit: dict, names: list, items: list) -> dict:
  """The v2 elements map: explicit entries as written, every other reference from the list."""
  panels = {i["metadata"]["name"]: i for i in items
            if i["kind"] == "Panel" and i["metadata"].get("annotations", {}).get(crs.RESOLVED) == "true"}
  libraries = {i["metadata"]["name"]: i for i in items if i["kind"] == "GrafanaLibraryPanel"}
  out = copy.deepcopy(explicit)
  for n in names:
    if n in out:
      continue
    if n in panels:
      out[n] = {"kind": "Panel", "spec": copy.deepcopy(panels[n]["spec"])}
    elif n in libraries:
      lp = libraries[n]
      model = json.loads(lp["spec"]["json"])
      out[n] = {"kind": "LibraryPanel", "spec": {"title": model.get("title", ""),
                                                 "libraryPanel": {"uid": lp["spec"]["uid"], "name": model["name"]}}}
    else:
      raise ElementNotFound(f"dashboard {dashboard}: element {n} is not in elements, and no resolved Panel or "
                            f"GrafanaLibraryPanel is named {n}; panels: {sorted(panels)}, "
                            f"library panels: {sorted(libraries)}")
  used = {e["spec"]["id"] for e in out.values() if "id" in e.get("spec", {})}
  next_id = 1
  for n in names + [k for k in out if k not in names]:
    s = out[n]["spec"]
    if "id" not in s:
      while next_id in used:
        next_id += 1
      s["id"] = next_id
      used.add(next_id)
  return out
