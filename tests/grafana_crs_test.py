import json
from kubed.kustomize.grafana import crs


def test_defaults_and_overrides():
  assert crs.common({}) == {"instanceSelector": {"matchLabels": {"app.kubernetes.io/name": "grafana"}},
                            "allowCrossNamespaceImport": True}
  assert crs.common({"allowCrossNamespaceImport": False})["allowCrossNamespaceImport"] is False


def test_meta_carries_namespace_labels_and_the_authoring_kind():
  assert crs.meta("redis", "Dashboard", "observe", {"a": "b"}) == {
    "name": "redis", "namespace": "observe", "labels": {"a": "b"},
    "annotations": {"grafana.krm.kubed.io/kind": "Dashboard"}}
  assert crs.meta("x", "Panel") == {"name": "x", "annotations": {"grafana.krm.kubed.io/kind": "Panel"}}


def test_library_panel_cr_carries_uid_and_name_in_the_model():
  cr = crs.library_panel_cr({}, crs.meta("cpu", "Panel"), {"type": "stat", "title": "CPU"}, "cpu", "CPU", "apps")
  assert cr["kind"] == "GrafanaLibraryPanel" and cr["metadata"]["name"] == "cpu"
  assert cr["spec"]["uid"] == "cpu" and cr["spec"]["folderUID"] == "apps"
  assert json.loads(cr["spec"]["json"]) == {"type": "stat", "title": "CPU", "uid": "cpu", "name": "CPU"}


def test_manifest_cr_wraps_a_v2_dashboard_with_library_defaults_and_dashboard_overrides():
  cr = crs.manifest_cr({"resyncPeriod": "12h"}, crs.meta("redis", "Dashboard", "observe"), {"title": "Redis"}, "apps",
                       {"patch": {"scripts": ["."]}})
  assert cr["kind"] == "GrafanaManifest" and cr["metadata"]["namespace"] == "observe"
  assert cr["spec"]["resyncPeriod"] == "12h" and cr["spec"]["patch"] == {"scripts": ["."]}
  assert cr["spec"]["template"] == {"apiVersion": "dashboard.grafana.app/v2", "kind": "Dashboard",
                                    "metadata": {"name": "redis", "annotations": {"grafana.app/folder": "apps"}},
                                    "spec": {"title": "Redis"}}
  assert crs.manifest_cr({}, crs.meta("r", "Dashboard"), {}, "f", {"resyncPeriod": "1h"})["spec"]["resyncPeriod"] == "1h"
  assert crs.manifest_cr({}, crs.meta("r", "Dashboard"), {}, "f", {})["spec"]["resyncPeriod"] == "24h"


def test_folder_cr():
  cr = crs.folder_cr({}, crs.meta("redis", "GrafanaLibrary"), "redis", "Redis", "parent")
  assert cr["kind"] == "GrafanaFolder"
  assert (cr["spec"]["uid"], cr["spec"]["title"], cr["spec"]["parentFolderUID"]) == ("redis", "Redis", "parent")
  assert "parentFolderUID" not in crs.folder_cr({}, crs.meta("r", "GrafanaLibrary"), "r", "R")["spec"]
