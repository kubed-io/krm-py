from kubed.krm import common as c
from kubed.kustomize.grafana import crs, folder


def src(kind, name, spec=None, labels=None):
  meta = {"name": name}
  if labels:
    meta["labels"] = labels
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": kind, "metadata": meta, "spec": spec or {}}


def cfg(name, spec):
  konfig = src("Folder", name, spec)
  konfig["metadata"]["annotations"] = {"config.kubernetes.io/function": "exec:\n  path: kubectl-kubed\n"}
  return konfig


def run(konfig, items):
  return folder.transform(c.new_resource_list_object(konfig, items))


def test_a_folder_places_what_it_selects_by_labels():
  dash = crs.manifest_cr(src("Dashboard", "redis", labels={"f": "apps"}), {})
  lib = crs.library_panel_cr(src("Panel", "cpu", labels={"f": "apps"}), {}, "cpu", "CPU")
  other = crs.manifest_cr(src("Dashboard", "emby"), {})
  items = run(cfg("apps", {"target": {"matchLabels": {"f": "apps"}}}), [dash, lib, other])["items"]
  assert crs.folder_of(items[0]) == "apps" and crs.folder_of(items[1]) == "apps"
  assert crs.folder_of(items[2]) is None
  assert items[3]["kind"] == "GrafanaFolder" and items[3]["spec"]["uid"] == "apps"


def test_kind_in_the_target_means_the_authoring_kind():
  dash = crs.manifest_cr(src("Dashboard", "redis"), {})
  lib = crs.library_panel_cr(src("Panel", "cpu"), {}, "cpu", "CPU")
  items = run(cfg("apps", {"target": {"kind": "Dashboard$"}}), [dash, lib])["items"]
  assert crs.folder_of(items[0]) == "apps" and crs.folder_of(items[1]) is None


def test_an_explicit_folder_wins_with_a_warning():
  dash = crs.manifest_cr(src("Dashboard", "redis"), {}, "elsewhere")
  krm = run(cfg("apps", {"target": {"name": "redis$"}}), [dash])
  assert crs.folder_of(krm["items"][0]) == "elsewhere"
  assert krm["results"][0]["severity"] == "warning" and "elsewhere" in krm["results"][0]["message"]


def test_folders_nest_by_selecting_folders():
  child = crs.folder_cr(src("Folder", "redis"))
  items = run(cfg("apps", {"target": {"kind": "Folder$", "name": "redis$"}}), [child])["items"]
  assert items[0]["spec"]["parentFolderUID"] == "apps"
