import json
import pytest
from kubed.krm import common as c
from kubed.krm.errors import ElementNotFound, LibraryError
from kubed.kustomize.grafana import library

API = "grafana.krm.kubed.io/v1alpha1"
LOCAL = "config.kubernetes.io/local-config"
QUERY = {"kind": "DataQuery", "group": "prometheus", "version": "v0", "datasource": {"name": "prom"},
         "spec": {"expr": "up"}}


def panel_spec(title="Memory"):
  return {"title": title, "vizConfig": {"kind": "VizConfig", "group": "stat", "spec": {}}}


def resource(kind, name, spec=None, labels=None, annotations=None, **body):
  meta = {"name": name}
  if labels:
    meta["labels"] = labels
  if annotations:
    meta["annotations"] = annotations
  out = {"apiVersion": API, "kind": kind, "metadata": meta, **body}
  if spec is not None:
    out["spec"] = spec
  return out


def ref(name):
  return {"kind": "GridLayoutItem", "spec": {"x": 0, "y": 0, "width": 12, "height": 8,
                                             "element": {"kind": "ElementReference", "name": name}}}


def layout(*names):
  return {"kind": "GridLayout", "spec": {"items": [ref(n) for n in names]}}


def dashboard(name="redis", *names, labels=None, **spec):
  return resource("Dashboard", name, {"title": name, "layout": layout(*names), **spec},
                  labels=labels or {"grafana.kubed.io/dashboard": "redis"})


def lib(name="redis", namespace="observe", **spec):
  spec.setdefault("folder", {"uid": "apps"})
  spec.setdefault("dashboards", {"matchLabels": {"grafana.kubed.io/dashboard": "redis"}})
  return {"apiVersion": API, "kind": "GrafanaLibrary",
          "metadata": {"name": name, "namespace": namespace,
                       "annotations": {"config.kubernetes.io/function": "exec:\n  path: kubectl-kubed\n"}},
          "spec": spec}


def run(konfig, items):
  return library.transform(c.new_resource_list_object(konfig, items))


def outputs(krm, kind):
  return [i for i in krm["items"] if i["kind"] == kind]


def local(krm):
  return sorted(i["metadata"]["name"] for i in krm["items"] if i["metadata"].get("annotations", {}).get(LOCAL))


def test_selected_panels_become_library_panels_in_the_librarys_folder():
  krm = run(lib(panels={"matchLabels": {"lib": "yes"}}),
            [resource("Panel", "cpu", panel_spec("CPU"), {"lib": "yes"}), resource("Panel", "memory", panel_spec())])
  [lp] = outputs(krm, "GrafanaLibraryPanel")
  assert (lp["metadata"]["name"], lp["metadata"]["namespace"]) == ("cpu", "observe")
  assert (lp["spec"]["uid"], lp["spec"]["folderUID"]) == ("cpu", "apps")
  assert json.loads(lp["spec"]["json"])["name"] == "CPU"
  assert local(krm) == ["cpu"]   # memory was not used, so it is left to fail at apply time


def test_library_panel_name_falls_back_to_metadata_name_and_takes_the_annotation():
  krm = run(lib(panels={"name": ".*"}),
            [resource("Panel", "tile", panel_spec("")),
             resource("Panel", "masthead", panel_spec("x"), annotations={"grafana.krm.kubed.io/library-name": "App masthead"})])
  names = {lp["spec"]["uid"]: json.loads(lp["spec"]["json"])["name"] for lp in outputs(krm, "GrafanaLibraryPanel")}
  assert names == {"tile": "tile", "masthead": "App masthead"}


def test_a_dashboard_references_library_panels_and_embeds_other_panels():
  items = [resource("Panel", "cpu", panel_spec("CPU"), {"lib": "yes"}), resource("Panel", "memory", panel_spec()),
           dashboard("redis", "memory", "cpu")]
  krm = run(lib(panels={"matchLabels": {"lib": "yes"}}), items)
  [m] = outputs(krm, "GrafanaManifest")
  assert (m["metadata"]["name"], m["metadata"]["namespace"]) == ("redis", "observe")
  assert m["spec"]["template"]["metadata"]["annotations"] == {"grafana.app/folder": "apps"}
  els = m["spec"]["template"]["spec"]["elements"]
  assert els["memory"] == {"kind": "Panel", "spec": {**panel_spec(), "id": 1}}
  assert els["cpu"] == {"kind": "LibraryPanel", "spec": {"title": "CPU", "id": 2,
                                                          "libraryPanel": {"uid": "cpu", "name": "CPU"}}}
  assert local(krm) == ["cpu", "memory", "redis"]


def test_only_selected_dashboards_are_built():
  krm = run(lib(), [dashboard("redis"), dashboard("emby", labels={"grafana.kubed.io/dashboard": "emby"})])
  assert [m["metadata"]["name"] for m in outputs(krm, "GrafanaManifest")] == ["redis"]
  assert local(krm) == ["redis"]


def test_only_our_apiversion_is_a_candidate():
  operator = {"apiVersion": "grafana.integreatly.org/v1beta1", "kind": "Dashboard",
              "metadata": {"name": "other", "labels": {"grafana.kubed.io/dashboard": "redis"}}, "spec": {}}
  krm = run(lib(), [operator])
  assert outputs(krm, "GrafanaManifest") == [] and krm["items"][0] == operator


def test_no_selector_selects_nothing():
  krm = run(lib(dashboards=None), [dashboard("redis"), resource("Panel", "cpu", panel_spec())])
  assert outputs(krm, "GrafanaManifest") == [] and outputs(krm, "GrafanaLibraryPanel") == [] and local(krm) == []


def test_an_existing_folder_is_only_referenced():
  assert outputs(run(lib(folder={"uid": "apps"}), []), "GrafanaFolder") == []


def test_a_titled_folder_is_created_with_the_librarys_name_as_uid():
  krm = run(lib(folder={"title": "Redis", "parent": "apps"}), [dashboard("redis")])
  [f] = outputs(krm, "GrafanaFolder")
  assert (f["spec"]["uid"], f["spec"]["title"], f["spec"]["parentFolderUID"]) == ("redis", "Redis", "apps")
  assert outputs(krm, "GrafanaManifest")[0]["spec"]["template"]["metadata"]["annotations"] == {"grafana.app/folder": "redis"}


def test_a_library_without_a_folder_fails():
  with pytest.raises(LibraryError, match="spec.folder"):
    run(lib(folder={}), [])


def test_an_earlier_librarys_panels_are_referenced_by_name():
  first = run(lib("shared", panels={"name": "masthead$"}, dashboards=None), [resource("Panel", "masthead", panel_spec("App"))])
  krm = run(lib("redis"), first["items"] + [dashboard("redis", "masthead")])
  els = outputs(krm, "GrafanaManifest")[0]["spec"]["template"]["spec"]["elements"]
  assert els["masthead"]["kind"] == "LibraryPanel"


def test_an_unknown_element_names_what_exists():
  with pytest.raises(ElementNotFound, match="memory"):
    run(lib(), [resource("Panel", "memory", panel_spec()), dashboard("redis", "nope")])


def test_explicit_elements_win_and_keep_their_ids():
  explicit = {"masthead": {"kind": "LibraryPanel", "spec": {"id": 1, "title": "App masthead",
                                                            "libraryPanel": {"uid": "app-masthead", "name": "App masthead"}}}}
  krm = run(lib(), [resource("Panel", "memory", panel_spec()), dashboard("redis", "masthead", "memory", elements=explicit)])
  els = outputs(krm, "GrafanaManifest")[0]["spec"]["template"]["spec"]["elements"]
  assert els["masthead"] == explicit["masthead"] and els["memory"]["spec"]["id"] == 2


def test_dashboard_overrides_leave_the_spec_and_shape_the_manifest():
  krm = run(lib(resyncPeriod="12h"), [dashboard("redis", resyncPeriod="1h", suspend=True)])
  m = outputs(krm, "GrafanaManifest")[0]
  assert (m["spec"]["resyncPeriod"], m["spec"]["suspend"]) == ("1h", True)
  assert set(m["spec"]["template"]["spec"]) == {"title", "layout", "elements"}


def test_targets_used_while_resolving_are_marked_local_config():
  dq = resource("DataQuery", "mem", labels={"p": "m"}, **{k: v for k, v in QUERY.items() if k != "kind"})
  unused = resource("DataQuery", "cpu", **{k: v for k, v in QUERY.items() if k != "kind"})
  memory = resource("Panel", "memory", {**panel_spec(), "data": {"kind": "QueryGroup", "spec": {"queries": [
    {"kind": "Target", "spec": {"kind": "DataQuery", "matchLabels": {"p": "m"}}}]}}})
  krm = run(lib(), [dq, unused, memory, dashboard("redis", "memory")])
  assert local(krm) == ["mem", "memory", "redis"]
  els = outputs(krm, "GrafanaManifest")[0]["spec"]["template"]["spec"]["elements"]
  assert els["memory"]["spec"]["data"]["spec"]["queries"][0]["spec"]["refId"] == "mem"


def test_rows_can_be_embedded_from_files(tmp_path):
  (tmp_path / "row.yaml").write_text(
    "kind: RowsLayoutRow\nspec:\n  title: Overview\n  layout:\n    kind: GridLayout\n    spec:\n      items:\n"
    "      - kind: GridLayoutItem\n        spec:\n          x: 0\n          y: 0\n          width: 24\n          height: 8\n"
    "          element:\n            kind: ElementReference\n            name: memory\n")
  d = resource("Dashboard", "redis", {"title": "R", "layout": {"kind": "RowsLayout", "spec": {"rows": [
    {"kind": "Embed", "spec": {"file": "row.yaml"}}]}}}, {"grafana.kubed.io/dashboard": "redis"},
    {"config.kubernetes.io/origin": f"path: {tmp_path}/dashboard.yaml\n"})
  spec = outputs(run(lib(), [resource("Panel", "memory", panel_spec()), d]), "GrafanaManifest")[0]["spec"]["template"]["spec"]
  assert spec["layout"]["spec"]["rows"][0]["spec"]["title"] == "Overview" and "memory" in spec["elements"]


def test_references_are_collected_in_first_appearance_order():
  tree = {"kind": "RowsLayout", "spec": {"rows": [
    {"kind": "RowsLayoutRow", "spec": {"layout": layout("b", "a")}},
    {"kind": "RowsLayoutRow", "spec": {"layout": layout("a", "c")}}]}}
  assert library.references(tree) == ["b", "a", "c"]


# Variables (round 2): node resolution is generic; these pin the contract for the
# variables list and a QueryVariable's query.

def const(name, value):
  return {"kind": "ConstantVariable", "spec": {"name": name, "query": value, "hide": "hideVariable"}}


def built_variables(variables, items=(), tmp_path=None):
  d = dashboard("redis", variables=variables)
  if tmp_path:
    d["metadata"]["annotations"] = {"config.kubernetes.io/origin": f"path: {tmp_path}/dashboard.yaml\n"}
  krm = run(lib(), [*items, d])
  return outputs(krm, "GrafanaManifest")[0]["spec"]["template"]["spec"]["variables"], krm


def test_a_multi_document_file_adds_every_variable_in_file_order(tmp_path):
  (tmp_path / "variables.yaml").write_text(
    "kind: ConstantVariable\nspec:\n  name: b\n  query: '2'\n---\n"
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: ConstantVariable\nmetadata:\n  name: a\nspec:\n  name: a\n  query: '1'\n")
  variables, _ = built_variables([{"kind": "Embed", "spec": {"file": "variables.yaml"}}], tmp_path=tmp_path)
  assert variables == [{"kind": "ConstantVariable", "spec": {"name": "b", "query": "2"}},
                       {"kind": "ConstantVariable", "spec": {"name": "a", "query": "1"}}]


def test_a_single_document_file_adds_one_variable_beside_inline_ones(tmp_path):
  (tmp_path / "pod.yaml").write_text("kind: ConstantVariable\nspec:\n  name: pod\n  query: redis-0\n")
  variables, _ = built_variables([const("first", "x"), {"kind": "Embed", "spec": {"file": "pod.yaml"}}], tmp_path=tmp_path)
  assert [v["spec"]["name"] for v in variables] == ["first", "pod"]


def test_a_target_adds_every_matching_variable_sorted_by_name_and_marks_them():
  items = [resource("ConstantVariable", "redis-b", const("b", "2")["spec"], {"dashboard": "redis"}),
           resource("ConstantVariable", "redis-a", const("a", "1")["spec"], {"dashboard": "redis"}),
           resource("ConstantVariable", "emby-a", const("e", "3")["spec"], {"dashboard": "emby"})]
  variables, krm = built_variables([{"kind": "Target", "spec": {"matchLabels": {"dashboard": "redis"}}}], items)
  assert variables == [const("a", "1"), const("b", "2")]
  assert local(krm) == ["redis", "redis-a", "redis-b"]


def test_a_target_can_add_just_one_variable():
  items = [resource("ConstantVariable", "redis-a", const("a", "1")["spec"]),
           resource("ConstantVariable", "redis-b", const("b", "2")["spec"])]
  variables, _ = built_variables([{"kind": "Target", "spec": {"name": "redis-b$"}}], items)
  assert variables == [const("b", "2")]


def test_a_query_variable_takes_its_query_from_a_file(tmp_path):
  (tmp_path / "pods.yaml").write_text(
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: DataQuery\nmetadata:\n  name: pods\n"
    "group: prometheus\nversion: v0\ndatasource:\n  name: prom\nspec:\n  expr: up\n")
  qv = {"kind": "QueryVariable", "spec": {"name": "pod", "query": {"kind": "Embed", "spec": {"file": "pods.yaml"}}}}
  variables, _ = built_variables([qv], tmp_path=tmp_path)
  assert variables[0]["spec"]["query"] == QUERY


def test_a_query_variable_takes_its_query_from_the_list():
  dq = resource("DataQuery", "pods", **{k: v for k, v in QUERY.items() if k != "kind"})
  qv = {"kind": "QueryVariable", "spec": {"name": "pod", "query": {"kind": "Target", "spec": {"kind": "DataQuery", "name": "pods$"}}}}
  variables, _ = built_variables([qv], [dq])
  assert variables[0]["spec"]["query"] == QUERY
