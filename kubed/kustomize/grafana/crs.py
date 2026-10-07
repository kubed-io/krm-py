"""The grafana-operator custom resources the grafana.krm.kubed.io functions emit."""
import copy
import json

OPERATOR = "grafana.integreatly.org/v1beta1"
KIND = "grafana.krm.kubed.io/kind"
LOCAL = "config.kubernetes.io/local-config"
RESOLVED = "grafana.krm.kubed.io/resolved"
FOLDER = "grafana.app/folder"
DEFAULT_SELECTOR = {"matchLabels": {"app.kubernetes.io/name": "grafana"}}


def common(spec: dict) -> dict:
  """The instance fields every operator CR carries, with the homelab defaults."""
  return {
    "instanceSelector": copy.deepcopy(spec.get("instanceSelector", DEFAULT_SELECTOR)),
    "allowCrossNamespaceImport": spec.get("allowCrossNamespaceImport", True),
  }


def meta(src: dict, name: str, kind: str) -> dict:
  """Output metadata: the source's labels and namespace, and the authoring kind it came from."""
  m = src["metadata"]
  out = {"name": name}
  if m.get("namespace"):
    out["namespace"] = m["namespace"]
  if m.get("labels"):
    out["labels"] = dict(m["labels"])
  out["annotations"] = {KIND: kind}
  return out


def library_panel_cr(src, model, uid, name, folder=None) -> dict:
  spec = {**common(src["spec"]), "uid": uid,
          "json": json.dumps({**model, "uid": uid, "name": name}, separators=(",", ":"), sort_keys=True)}
  if folder:
    spec["folderUID"] = folder
  return {"apiVersion": OPERATOR, "kind": "GrafanaLibraryPanel", "metadata": meta(src, uid, "Panel"), "spec": spec}


def manifest_cr(src, dashboard_spec, folder=None) -> dict:
  name = src["metadata"]["name"]
  s = src["spec"]
  template_meta = {"name": name}
  if folder:
    template_meta["annotations"] = {FOLDER: folder}
  spec = {**common(s), "resyncPeriod": s.get("resyncPeriod", "24h"), "template": {
    "apiVersion": "dashboard.grafana.app/v2", "kind": "Dashboard", "metadata": template_meta, "spec": dashboard_spec}}
  for k in ("suspend", "patch"):
    if k in s:
      spec[k] = s[k]
  return {"apiVersion": OPERATOR, "kind": "GrafanaManifest", "metadata": meta(src, name, "Dashboard"), "spec": spec}


def folder_cr(src) -> dict:
  name = src["metadata"]["name"]
  s = src["spec"]
  spec = {**common(s), "uid": name, "title": s.get("title", name)}
  if s.get("folder"):
    spec["parentFolderUID"] = s["folder"]
  if "permissions" in s:
    spec["permissions"] = s["permissions"]
  return {"apiVersion": OPERATOR, "kind": "GrafanaFolder", "metadata": meta(src, name, "Folder"), "spec": spec}


def folder_of(cr: dict):
  """The folder uid an emitted CR is placed in, or None."""
  if cr["kind"] == "GrafanaManifest":
    return cr["spec"]["template"]["metadata"].get("annotations", {}).get(FOLDER)
  if cr["kind"] == "GrafanaLibraryPanel":
    return cr["spec"].get("folderUID")
  if cr["kind"] == "GrafanaFolder":
    return cr["spec"].get("parentFolderUID")
  return None


def place(cr: dict, uid: str):
  """Put an emitted CR in the folder with this uid."""
  if cr["kind"] == "GrafanaManifest":
    cr["spec"]["template"]["metadata"].setdefault("annotations", {})[FOLDER] = uid
  elif cr["kind"] == "GrafanaLibraryPanel":
    cr["spec"]["folderUID"] = uid
  elif cr["kind"] == "GrafanaFolder":
    cr["spec"]["parentFolderUID"] = uid
