import pytest
from kubed.kustomize.grafana import nodes
from kubed.krm.errors import EmbedError, TargetError

QUERY = {"group": "prometheus", "version": "v0", "datasource": {"name": "prom"}, "spec": {"expr": "up"}}


def embed(file, **kw):
  return {"kind": "Embed", "spec": {"file": file, **kw}}


def target(**sel):
  return {"kind": "Target", "spec": sel}


def item(kind, name, labels=None, **body):
  meta = {"name": name, "annotations": {"config.kubernetes.io/local-config": "true"}}
  if labels:
    meta["labels"] = labels
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": kind, "metadata": meta, **body}


def test_other_kinds_pass_through_untouched():
  tree = {"kind": "GridLayout", "spec": {"items": [{"kind": "GridLayoutItem", "spec": {"x": 0}}]}}
  assert nodes.resolve(tree) == tree


def test_embed_text_fills_a_string_field(tmp_path):
  (tmp_path / "a.html").write_text("<b>hi</b>")
  assert nodes.resolve({"content": embed("a.html")}, str(tmp_path)) == {"content": "<b>hi</b>"}


def test_embed_yaml_becomes_an_object_without_its_krm_wrapping(tmp_path):
  (tmp_path / "row.yaml").write_text(
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: RowsLayoutRow\nmetadata:\n  name: r\nspec:\n  title: Overview\n")
  assert nodes.resolve({"layout": embed("row.yaml")}, str(tmp_path)) == {
    "layout": {"kind": "RowsLayoutRow", "spec": {"title": "Overview"}}}


def test_embed_nested_false_keeps_yaml_as_text(tmp_path):
  (tmp_path / "a.yaml").write_text("x: 1\n")
  assert nodes.resolve(embed("a.yaml", nested=False), str(tmp_path)) == "x: 1\n"


def test_embed_parse_serialises_to_json(tmp_path):
  (tmp_path / "a.yaml").write_text("x: 1\n")
  assert nodes.resolve(embed("a.yaml", parse="json"), str(tmp_path)) == '{"x": 1}'


def test_embed_glob_in_a_list_expands_sorted_by_path(tmp_path):
  (tmp_path / "rows").mkdir()
  (tmp_path / "rows" / "b.yaml").write_text("kind: RowsLayoutRow\nspec:\n  title: B\n")
  (tmp_path / "rows" / "a.yaml").write_text("kind: RowsLayoutRow\nspec:\n  title: A\n")
  rows = nodes.resolve({"rows": [embed("rows/*.yaml")]}, str(tmp_path))["rows"]
  assert [r["spec"]["title"] for r in rows] == ["A", "B"]


def test_embed_many_values_outside_a_list_fails(tmp_path):
  (tmp_path / "a.yaml").write_text("kind: X\n---\nkind: Y\n")
  with pytest.raises(EmbedError, match="exactly one"):
    nodes.resolve({"layout": embed("a.yaml")}, str(tmp_path))


def test_nested_embeds_resolve_next_to_their_own_file(tmp_path):
  (tmp_path / "rows").mkdir()
  (tmp_path / "rows" / "r.yaml").write_text(
    "kind: RowsLayoutRow\nspec:\n  title:\n    kind: Embed\n    spec:\n      file: title.txt\n")
  (tmp_path / "rows" / "title.txt").write_text("Nested")
  assert nodes.resolve(embed("rows/r.yaml"), str(tmp_path))["spec"]["title"] == "Nested"


def test_embed_cycle_fails(tmp_path):
  (tmp_path / "a.yaml").write_text("kind: Embed\nspec:\n  file: a.yaml\n")
  with pytest.raises(EmbedError, match="cycle"):
    nodes.resolve(embed("a.yaml"), str(tmp_path))


def test_missing_file_names_the_base(tmp_path):
  with pytest.raises(EmbedError, match="resolved against"):
    nodes.resolve(embed("nope.html"), str(tmp_path))


def test_remote_base_refuses_embed():
  with pytest.raises(EmbedError, match="remote base"):
    nodes.resolve(embed("a.html"), None)


def test_base_of_reads_the_origin_annotation():
  local = {"metadata": {"annotations": {"config.kubernetes.io/origin": "path: ../shared/panels/a.yaml\n"}}}
  remote = {"metadata": {"annotations": {
    "config.kubernetes.io/origin": "path: a.yaml\nrepo: https://github.com/x/y\nref: main\n"}}}
  assert nodes.base_of(local) == "../shared/panels"
  assert nodes.base_of({"metadata": {}}) == "."
  assert nodes.base_of(remote) is None


def test_target_outside_a_list_takes_its_one_match():
  items = [item("RowsLayout", "tabs", spec={"rows": []})]
  assert nodes.resolve({"layout": target(kind="RowsLayout", name="tabs$")}, ".", items) == {
    "layout": {"kind": "RowsLayout", "spec": {"rows": []}}}


def test_target_in_a_list_expands_sorted_by_name():
  items = [item("RowsLayoutRow", "b", {"d": "x"}, spec={"title": "B"}),
           item("RowsLayoutRow", "a", {"d": "x"}, spec={"title": "A"})]
  rows = nodes.resolve({"rows": [target(matchLabels={"d": "x"})]}, ".", items)["rows"]
  assert [r["spec"]["title"] for r in rows] == ["A", "B"]


def test_target_with_no_match_fails():
  with pytest.raises(TargetError, match="resolved to nothing"):
    nodes.resolve(target(name="nope"), ".", [item("RowsLayout", "tabs", spec={})])


def test_target_without_a_list_explains_generators():
  with pytest.raises(TargetError, match="transformers:"):
    nodes.resolve(target(name="x"), ".", [])


def test_target_two_matches_outside_a_list_fails():
  items = [item("RowsLayout", "a", spec={}), item("RowsLayout", "b", spec={})]
  with pytest.raises(TargetError, match="exactly one"):
    nodes.resolve({"layout": target(kind="RowsLayout")}, ".", items)


def test_target_matches_resolve_their_own_embeds(tmp_path):
  (tmp_path / "t.txt").write_text("From file")
  row = item("RowsLayoutRow", "r", spec={"title": {"kind": "Embed", "spec": {"file": "t.txt"}}})
  row["metadata"]["annotations"]["config.kubernetes.io/origin"] = f"path: {tmp_path}/row.yaml\n"
  assert nodes.resolve(target(name="r$"), ".", [row])["spec"]["title"] == "From file"


def test_dataqueries_in_a_queries_list_become_panel_queries_named_after_them():
  items = [item("DataQuery", "mem", {"p": "m"}, **QUERY), item("DataQuery", "cpu", {"p": "m"}, **QUERY)]
  queries = nodes.resolve({"queries": [target(kind="DataQuery", matchLabels={"p": "m"})]}, ".", items)["queries"]
  assert [q["spec"]["refId"] for q in queries] == ["cpu", "mem"]
  assert queries[0] == {"kind": "PanelQuery", "spec": {"refId": "cpu", "hidden": False,
                                                        "query": {"kind": "DataQuery", **QUERY}}}


def test_an_embedded_dataquery_file_in_queries_is_wrapped_too(tmp_path):
  (tmp_path / "q.yaml").write_text(
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: DataQuery\nmetadata:\n  name: up\n"
    "group: prometheus\nversion: v0\ndatasource:\n  name: prom\nspec:\n  expr: up\n")
  queries = nodes.resolve({"queries": [embed("q.yaml")]}, str(tmp_path))["queries"]
  assert queries == [{"kind": "PanelQuery", "spec": {"refId": "up", "hidden": False,
                                                     "query": {"kind": "DataQuery", **QUERY}}}]


def test_a_query_field_takes_one_dataquery_unwrapped():
  items = [item("DataQuery", "mem", **QUERY)]
  pq = {"kind": "PanelQuery", "spec": {"refId": "A", "query": target(kind="DataQuery", name="mem$")}}
  assert nodes.resolve(pq, ".", items)["spec"]["query"] == {"kind": "DataQuery", **QUERY}


def lp(name, uid=None, labels=None):
  return item("LibraryPanel", name, labels, spec={"id": 1, "title": name, "libraryPanel": {"uid": uid or name, "name": name}})


def test_a_target_in_elements_spreads_its_matches_keyed_by_name():
  items = [lp("b", labels={"t": "x"}), lp("a", labels={"t": "x"}), lp("c")]
  out = nodes.resolve({"elements": {"all": target(kind="LibraryPanel", matchLabels={"t": "x"}), "own": {"kind": "Panel"}}},
                      items=items)
  assert list(out["elements"]) == ["a", "b", "own"]
  assert out["elements"]["a"] == {"kind": "LibraryPanel", "spec": items[1]["spec"]}


def test_an_embed_in_elements_spreads_a_multi_document_file(tmp_path):
  (tmp_path / "els.yaml").write_text(
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: LibraryPanel\nmetadata:\n  name: one\nspec:\n  id: 1\n---\n"
    "apiVersion: grafana.krm.kubed.io/v1alpha1\nkind: LibraryPanel\nmetadata:\n  name: two\nspec:\n  id: 2\n")
  out = nodes.resolve({"elements": {"x": embed("els.yaml")}}, str(tmp_path))
  assert out == {"elements": {"one": {"kind": "LibraryPanel", "spec": {"id": 1}},
                              "two": {"kind": "LibraryPanel", "spec": {"id": 2}}}}


def test_a_name_defined_twice_in_elements_fails():
  with pytest.raises(TargetError, match="more than once"):
    nodes.resolve({"elements": {"a": {"kind": "Panel"}, "all": target(kind="LibraryPanel")}}, items=[lp("a")])
