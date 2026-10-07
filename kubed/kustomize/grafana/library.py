"""GrafanaLibrary: the one grafana.krm.kubed.io function.

A transformer. Its `panels` selector picks the Panels that become library panels and
its `dashboards` selector the Dashboards it builds; everything lands in its one folder.
Only grafana.krm.kubed.io resources are candidates - operator kinds already in the
list are finished. Whatever it uses is marked local-config and left for kustomize to
drop; a resource of ours that no library used reaches the cluster and fails there.
"""
import copy
import json
from kubed.krm import common as c
from kubed.krm.errors import ElementNotFound, LibraryError
from kubed.kustomize.grafana import convert, crs, nodes

GROUP = "grafana.krm.kubed.io/"
LIBRARY_NAME = "grafana.krm.kubed.io/library-name"
OVERRIDES = ("resyncPeriod", "suspend", "patch")


def transform(krm: dict) -> dict:
  konfig = krm["functionConfig"]
  library = konfig["spec"]
  namespace = konfig["metadata"].get("namespace")
  items = krm["items"]
  ours = [i for i in items if str(i.get("apiVersion", "")).startswith(GROUP)]
  used = set()
  folder = _folder(konfig)
  out = []

  for p in _select(ours, "Panel", library.get("panels")):
    name = p["metadata"]["name"]
    spec = nodes.resolve(copy.deepcopy(p["spec"]), nodes.base_of(p), items, used=used)
    label = p["metadata"].get("annotations", {}).get(LIBRARY_NAME) or spec.get("title") or name
    out.append(crs.library_panel_cr(library, crs.meta(name, "Panel", namespace, p["metadata"].get("labels")),
                                    convert.to_v1(spec, name), name, label, folder["uid"]))
    used.add(("Panel", name))

  for d in _select(ours, "Dashboard", library.get("dashboards")):
    name = d["metadata"]["name"]
    spec = nodes.resolve(copy.deepcopy(d["spec"]), nodes.base_of(d), items, used=used)
    overrides = {k: spec.pop(k) for k in OVERRIDES if k in spec}
    spec["elements"] = elements(name, spec.get("elements", {}), references(spec.get("layout", {})),
                                items + out, ours, used)
    out.append(crs.manifest_cr(library, crs.meta(name, "Dashboard", namespace, d["metadata"].get("labels")),
                               spec, folder["uid"], overrides))
    used.add(("Dashboard", name))

  if folder.get("title"):
    out.append(crs.folder_cr(library, crs.meta(folder["uid"], "GrafanaLibrary", namespace,
                                               konfig["metadata"].get("labels")),
                             folder["uid"], folder["title"], folder.get("parent")))

  for i in ours:
    if (i["kind"], i["metadata"]["name"]) in used:
      i["metadata"].setdefault("annotations", {})[crs.LOCAL] = "true"
  krm["items"] = items + out
  return krm


def _folder(konfig) -> dict:
  """{uid, title?, parent?}: an existing folder by uid, or one to create (uid defaults to the library's name)."""
  f = konfig["spec"].get("folder") or {}
  if f.get("title"):
    return {"uid": f.get("uid") or konfig["metadata"]["name"], "title": f["title"], "parent": f.get("parent")}
  if f.get("uid"):
    return {"uid": f["uid"]}
  raise LibraryError(f"GrafanaLibrary {konfig['metadata']['name']}: spec.folder needs a uid (an existing folder) "
                     "or a title (a folder to create)")


def _select(ours, kind, selector):
  """The resources of one kind a selector matches; no selector matches none."""
  if not selector:
    return []
  return [i for i in ours if i["kind"] == kind and c.targeted(i, {**selector, "kind": f"{kind}$"})]


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


def elements(dashboard: str, explicit: dict, names: list, items: list, ours: list, used: set) -> dict:
  """The v2 elements map: explicit entries as written; then by name a library panel (a reference)
  or any other Panel of ours (embedded)."""
  libraries = {i["metadata"]["name"]: i for i in items if i.get("kind") == "GrafanaLibraryPanel"}
  panels = {i["metadata"]["name"]: i for i in ours if i["kind"] == "Panel"}
  out = copy.deepcopy(explicit)
  for n in names:
    if n in out:
      continue
    if n in libraries:
      lp = libraries[n]
      model = json.loads(lp["spec"]["json"])
      out[n] = {"kind": "LibraryPanel", "spec": {"title": model.get("title", ""),
                                                 "libraryPanel": {"uid": lp["spec"]["uid"], "name": model["name"]}}}
    elif n in panels:
      p = panels[n]
      out[n] = {"kind": "Panel", "spec": nodes.resolve(copy.deepcopy(p["spec"]), nodes.base_of(p), items, used=used)}
      used.add(("Panel", n))
    else:
      raise ElementNotFound(f"dashboard {dashboard}: element {n} is not in elements, and no Panel or "
                            f"GrafanaLibraryPanel is named {n}; panels: {sorted(panels)}, "
                            f"library panels: {sorted(libraries)}")
  taken = {e["spec"]["id"] for e in out.values() if "id" in e.get("spec", {})}
  next_id = 1
  for n in names + [k for k in out if k not in names]:
    s = out[n]["spec"]
    if "id" not in s:
      while next_id in taken:
        next_id += 1
      s["id"] = next_id
      taken.add(next_id)
  return out
