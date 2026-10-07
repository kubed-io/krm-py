import json
from kubed.kustomize.grafana import crs


def src(kind, name, spec, namespace=None, labels=None):
  meta = {"name": name, "annotations": {"config.kubernetes.io/function": "exec:\n  path: kubectl-kubed\n"}}
  if namespace:
    meta["namespace"] = namespace
  if labels:
    meta["labels"] = labels
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": kind, "metadata": meta, "spec": spec}


def test_defaults_and_overrides():
  assert crs.common({}) == {"instanceSelector": {"matchLabels": {"app.kubernetes.io/name": "grafana"}},
                            "allowCrossNamespaceImport": True}
  assert crs.common({"allowCrossNamespaceImport": False})["allowCrossNamespaceImport"] is False


def test_meta_copies_labels_and_namespace_but_not_function_annotations():
  m = crs.meta(src("Dashboard", "redis", {}, "observe", {"a": "b"}), "redis", "Dashboard")
  assert m == {"name": "redis", "namespace": "observe", "labels": {"a": "b"},
               "annotations": {"grafana.krm.kubed.io/kind": "Dashboard"}}


def test_library_panel_cr_carries_uid_and_name_in_the_model():
  cr = crs.library_panel_cr(src("Panel", "cpu", {}), {"type": "stat", "title": "CPU"}, "cpu", "CPU", "apps")
  assert cr["kind"] == "GrafanaLibraryPanel" and cr["metadata"]["name"] == "cpu"
  assert cr["spec"]["uid"] == "cpu" and cr["spec"]["folderUID"] == "apps"
  assert json.loads(cr["spec"]["json"]) == {"type": "stat", "title": "CPU", "uid": "cpu", "name": "CPU"}


def test_manifest_cr_wraps_a_v2_dashboard():
  cr = crs.manifest_cr(src("Dashboard", "redis", {"patch": {"scripts": ["."]}}, "observe"), {"title": "Redis"}, "apps")
  assert cr["kind"] == "GrafanaManifest" and cr["metadata"]["namespace"] == "observe"
  assert cr["spec"]["resyncPeriod"] == "24h"
  assert cr["spec"]["patch"] == {"scripts": ["."]}
  assert cr["spec"]["template"] == {"apiVersion": "dashboard.grafana.app/v2", "kind": "Dashboard",
                                    "metadata": {"name": "redis", "annotations": {"grafana.app/folder": "apps"}},
                                    "spec": {"title": "Redis"}}


def test_folder_cr_takes_its_name_as_uid():
  cr = crs.folder_cr(src("Folder", "apps", {"folder": "parent"}))
  assert cr["spec"]["uid"] == "apps" and cr["spec"]["title"] == "apps"
  assert cr["spec"]["parentFolderUID"] == "parent"


def test_place_and_folder_of_cover_every_cr():
  for cr in (crs.manifest_cr(src("Dashboard", "d", {}), {}),
             crs.library_panel_cr(src("Panel", "p", {}), {}, "p", "P"),
             crs.folder_cr(src("Folder", "f", {}))):
    assert crs.folder_of(cr) is None
    crs.place(cr, "apps")
    assert crs.folder_of(cr) == "apps"
