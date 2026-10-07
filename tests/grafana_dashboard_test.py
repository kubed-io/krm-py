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


# Round 2: variables. Node resolution is generic; these pin the contract for the
# variables list and a QueryVariable's query.

QUERY = {"kind": "DataQuery", "group": "prometheus", "version": "v0", "datasource": {"name": "prom"},
         "spec": {"query": "label_values(up, pod)"}}


def const(name, value):
  return {"kind": "ConstantVariable", "spec": {"name": name, "query": value, "hide": "hideVariable"}}


def variable_resource(kind, name, spec, labels=None):
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": kind,
          "metadata": {"name": name, "labels": labels or {"dashboard": "redis"},
                       "annotations": {"config.kubernetes.io/local-config": "true"}}, "spec": spec}


def built_variables(spec, items, tmp_path=None):
  konfig = cfg({"title": "R", "layout": layout(), **spec})
  if tmp_path:
    konfig["metadata"]["annotations"]["config.kubernetes.io/origin"] = f"path: {tmp_path}/dashboard.yaml\n"
  out = dashboard.transform(c.new_resource_list_object(konfig, items))["items"]
  return out[-1]["spec"]["template"]["spec"]["variables"]


def test_a_multi_document_file_adds_every_variable_in_file_order(tmp_path):
  (tmp_path / "variables.yaml").write_text(
    "kind: ConstantVariable\nspec:\n  name: b\n  query: '2'\n---\n"
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: ConstantVariable\nmetadata:\n  name: a\nspec:\n  name: a\n  query: '1'\n")
  variables = built_variables({"variables": [{"kind": "Embed", "spec": {"file": "variables.yaml"}}]}, [], tmp_path)
  assert variables == [{"kind": "ConstantVariable", "spec": {"name": "b", "query": "2"}},
                       {"kind": "ConstantVariable", "spec": {"name": "a", "query": "1"}}]


def test_a_single_document_file_adds_one_variable_beside_inline_ones(tmp_path):
  (tmp_path / "pod.yaml").write_text("kind: ConstantVariable\nspec:\n  name: pod\n  query: redis-0\n")
  variables = built_variables({"variables": [const("first", "x"), {"kind": "Embed", "spec": {"file": "pod.yaml"}}]},
                              [], tmp_path)
  assert [v["spec"]["name"] for v in variables] == ["first", "pod"]


def test_a_target_adds_every_matching_variable_sorted_by_name():
  items = [variable_resource("ConstantVariable", "redis-b", const("b", "2")["spec"]),
           variable_resource("ConstantVariable", "redis-a", const("a", "1")["spec"]),
           variable_resource("ConstantVariable", "emby-a", const("e", "3")["spec"], {"dashboard": "emby"})]
  variables = built_variables({"variables": [{"kind": "Target", "spec": {"matchLabels": {"dashboard": "redis"}}}]}, items)
  assert variables == [const("a", "1"), const("b", "2")]


def test_a_target_can_add_just_one_variable():
  items = [variable_resource("ConstantVariable", "redis-a", const("a", "1")["spec"]),
           variable_resource("ConstantVariable", "redis-b", const("b", "2")["spec"])]
  variables = built_variables({"variables": [{"kind": "Target", "spec": {"name": "redis-b$"}}]}, items)
  assert variables == [const("b", "2")]


def test_a_query_variable_takes_its_query_from_a_file(tmp_path):
  (tmp_path / "pods.yaml").write_text(
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: DataQuery\nmetadata:\n  name: pods\n"
    "group: prometheus\nversion: v0\ndatasource:\n  name: prom\nspec:\n  query: label_values(up, pod)\n")
  qv = {"kind": "QueryVariable", "spec": {"name": "pod", "query": {"kind": "Embed", "spec": {"file": "pods.yaml"}}}}
  assert built_variables({"variables": [qv]}, [], tmp_path)[0]["spec"]["query"] == QUERY


def test_a_query_variable_takes_its_query_from_the_list():
  dq = {"apiVersion": "grafana.krm.kubed.io/v1alpha1",
        "metadata": {"name": "pods", "annotations": {"config.kubernetes.io/local-config": "true"}}, **QUERY}
  qv = {"kind": "QueryVariable", "spec": {"name": "pod", "query": {"kind": "Target", "spec": {"kind": "DataQuery", "name": "pods$"}}}}
  assert built_variables({"variables": [qv]}, [dq])[0]["spec"]["query"] == QUERY
