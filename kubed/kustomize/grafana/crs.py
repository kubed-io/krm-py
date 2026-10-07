"""The grafana-operator custom resources a GrafanaLibrary emits."""
import copy
import json

OPERATOR = "grafana.integreatly.org/v1beta1"
KIND = "grafana.krm.kubed.io/kind"
LOCAL = "config.kubernetes.io/local-config"
FOLDER = "grafana.app/folder"
DEFAULT_SELECTOR = {"matchLabels": {"app.kubernetes.io/name": "grafana"}}


def common(spec: dict) -> dict:
  """The instance fields every operator CR carries, with the homelab defaults."""
  return {
    "instanceSelector": copy.deepcopy(spec.get("instanceSelector", DEFAULT_SELECTOR)),
    "allowCrossNamespaceImport": spec.get("allowCrossNamespaceImport", True),
  }


def meta(name: str, kind: str, namespace=None, labels=None) -> dict:
  """Output metadata, marked with the authoring kind it came from."""
  out = {"name": name}
  if namespace:
    out["namespace"] = namespace
  if labels:
    out["labels"] = dict(labels)
  out["annotations"] = {KIND: kind}
  return out


def library_panel_cr(library: dict, metadata: dict, model: dict, uid: str, name: str, folder: str) -> dict:
  spec = {**common(library), "uid": uid, "folderUID": folder,
          "json": json.dumps({**model, "uid": uid, "name": name}, separators=(",", ":"), sort_keys=True)}
  return {"apiVersion": OPERATOR, "kind": "GrafanaLibraryPanel", "metadata": metadata, "spec": spec}


def manifest_cr(library: dict, metadata: dict, dashboard_spec: dict, folder: str, overrides: dict) -> dict:
  """A GrafanaManifest holding a dashboard.grafana.app/v2 Dashboard; its uid is the manifest's name."""
  spec = {**common(library), "resyncPeriod": overrides.get("resyncPeriod", library.get("resyncPeriod", "24h")),
          "template": {"apiVersion": "dashboard.grafana.app/v2", "kind": "Dashboard",
                       "metadata": {"name": metadata["name"], "annotations": {FOLDER: folder}},
                       "spec": dashboard_spec}}
  for k in ("suspend", "patch"):
    if k in overrides:
      spec[k] = overrides[k]
  return {"apiVersion": OPERATOR, "kind": "GrafanaManifest", "metadata": metadata, "spec": spec}


def folder_cr(library: dict, metadata: dict, uid: str, title: str, parent=None) -> dict:
  spec = {**common(library), "uid": uid, "title": title}
  if parent:
    spec["parentFolderUID"] = parent
  return {"apiVersion": OPERATOR, "kind": "GrafanaFolder", "metadata": metadata, "spec": spec}
