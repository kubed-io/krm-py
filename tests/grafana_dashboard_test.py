import pytest
from kubed.krm import common as c
from kubed.krm.errors import ElementNotFound
from kubed.kustomize.grafana import crs, dashboard

PANEL_SPEC = {"title": "Memory", "vizConfig": {"kind": "VizConfig", "group": "stat", "spec": {}}}


def ref(name):
  return {"kind": "GridLayoutItem", "spec": {"x": 0, "y": 0, "width": 12, "height": 8,
                                             "element": {"kind": "ElementReference", "name": name}}}


def layout(*names):
  return {"kind": "GridLayout", "spec": {"items": [ref(n) for n in names]}}


def cfg(spec, name="redis", namespace="observe"):
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": "Dashboard",
          "metadata": {"name": name, "namespace": namespace,
                       "annotations": {"config.kubernetes.io/function": "exec:\n  path: kubectl-kubed\n"}},
          "spec": spec}


def local_panel(name, spec=PANEL_SPEC):
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": "Panel",
          "metadata": {"name": name, "annotations": {crs.LOCAL: "true", crs.RESOLVED: "true"}}, "spec": spec}


def library(name, title):
  src = {"metadata": {"name": name}, "spec": {}}
  return crs.library_panel_cr(src, {"type": "stat", "title": title}, name, title)


def run(spec, items):
  return dashboard.transform(c.new_resource_list_object(cfg(spec), items))["items"]


def test_references_are_collected_in_first_appearance_order():
  tree = {"kind": "RowsLayout", "spec": {"rows": [
    {"kind": "RowsLayoutRow", "spec": {"layout": layout("b", "a")}},
    {"kind": "RowsLayoutRow", "spec": {"layout": layout("a", "c")}}]}}
  assert dashboard.references(tree) == ["b", "a", "c"]


def test_local_panels_embed_and_library_panels_reference():
  items = [local_panel("memory"), library("cpu", "CPU")]
  out = run({"title": "Redis", "layout": layout("memory", "cpu")}, items)
  assert out[:2] == items
  m = out[2]
  assert (m["kind"], m["metadata"]["name"], m["metadata"]["namespace"]) == ("GrafanaManifest", "redis", "observe")
  els = m["spec"]["template"]["spec"]["elements"]
  assert els["memory"] == {"kind": "Panel", "spec": {**PANEL_SPEC, "id": 1}}
  assert els["cpu"] == {"kind": "LibraryPanel", "spec": {"title": "CPU", "id": 2,
                                                          "libraryPanel": {"uid": "cpu", "name": "CPU"}}}


def test_explicit_elements_win_and_keep_their_ids():
  explicit = {"masthead": {"kind": "LibraryPanel",
                           "spec": {"id": 1, "title": "App masthead",
                                    "libraryPanel": {"uid": "app-masthead", "name": "App masthead"}}}}
  out = run({"title": "R", "elements": explicit, "layout": layout("masthead", "memory")}, [local_panel("memory")])
  els = out[-1]["spec"]["template"]["spec"]["elements"]
  assert els["masthead"] == explicit["masthead"]
  assert els["memory"]["spec"]["id"] == 2


def test_an_unknown_element_names_what_exists():
  with pytest.raises(ElementNotFound, match="memory"):
    run({"title": "R", "layout": layout("nope")}, [local_panel("memory")])


def test_krm_fields_leave_the_dashboard_and_shape_the_manifest():
  out = run({"title": "R", "folder": "apps", "resyncPeriod": "1h", "layout": layout()}, [])
  m = out[-1]
  assert m["spec"]["resyncPeriod"] == "1h"
  assert m["spec"]["template"]["metadata"]["annotations"] == {"grafana.app/folder": "apps"}
  assert m["spec"]["template"]["spec"] == {"title": "R", "layout": layout(), "elements": {}}


def test_rows_can_be_embedded_from_files(tmp_path):
  (tmp_path / "row.yaml").write_text(
    "kind: RowsLayoutRow\nspec:\n  title: Overview\n  layout:\n    kind: GridLayout\n    spec:\n      items:\n"
    "      - kind: GridLayoutItem\n        spec:\n          x: 0\n          y: 0\n          width: 24\n          height: 8\n"
    "          element:\n            kind: ElementReference\n            name: memory\n")
  konfig = cfg({"title": "R", "layout": {"kind": "RowsLayout", "spec": {"rows": [
    {"kind": "Embed", "spec": {"file": "row.yaml"}}]}}})
  konfig["metadata"]["annotations"]["config.kubernetes.io/origin"] = f"path: {tmp_path}/dashboard.yaml\n"
  out = dashboard.transform(c.new_resource_list_object(konfig, [local_panel("memory")]))["items"]
  spec = out[-1]["spec"]["template"]["spec"]
  assert spec["layout"]["spec"]["rows"][0]["spec"]["title"] == "Overview"
  assert "memory" in spec["elements"]
