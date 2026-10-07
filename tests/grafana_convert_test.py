import json
import os
import pytest
from kubed.kustomize.grafana import convert
from kubed.krm.errors import ConversionError

# The live Redis dashboard's spec, captured 2026-10-07: as stored (v2), and as
# Grafana itself converts it (v1).
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "grafana")


def load(version):
  with open(os.path.join(FIXTURES, f"redis.{version}.json")) as fh:
    return json.load(fh)


def v1_panels():
  """Grafana's v1 panels by id, layout fields removed; collapsed rows nest theirs."""
  out = {}
  for p in load("v1")["panels"]:
    for q in [p] + p.get("panels", []):
      if q.get("type") not in ("row", "library-panel-ref") and "libraryPanel" not in q:
        out[q["id"]] = {k: v for k, v in q.items() if k not in ("id", "gridPos")}
  return out


V2 = [e["spec"] for e in load("v2")["elements"].values() if e["kind"] == "Panel"]
V1 = v1_panels()


@pytest.mark.parametrize("spec", V2, ids=[str(s["id"]) for s in V2])
def test_matches_grafanas_own_v1_conversion(spec):
  assert convert.to_v1(spec) == V1[spec["id"]]


def query(ds, hidden=False, ref="A"):
  return {"kind": "PanelQuery", "spec": {"refId": ref, "hidden": hidden, "query": {
    "kind": "DataQuery", "group": "prometheus", "version": "v0", "datasource": {"name": ds}, "spec": {"expr": "up"}}}}


def panel(queries, **data):
  return {"title": "t", "vizConfig": {"kind": "VizConfig", "group": "stat", "spec": {}},
          "data": {"kind": "QueryGroup", "spec": {"queries": queries, **data}}}


def test_a_hidden_query_becomes_hide():
  assert convert.to_v1(panel([query("p", hidden=True)]))["targets"] == [
    {"datasource": {"type": "prometheus", "uid": "p"}, "expr": "up", "refId": "A", "hide": True}]


def test_mixed_datasources_leave_the_panel_datasource_unset():
  assert "datasource" not in convert.to_v1(panel([query("a"), query("b", ref="B")]))


def test_query_options_lift_to_the_panel():
  v1 = convert.to_v1(panel([query("p")], queryOptions={"maxDataPoints": 100, "interval": "1m"}))
  assert (v1["maxDataPoints"], v1["interval"]) == (100, "1m")


def test_a_panel_without_a_viz_group_fails():
  with pytest.raises(ConversionError, match="vizConfig.group"):
    convert.to_v1({"title": "t"}, "p")
