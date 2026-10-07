import copy
import json
from kubed.krm import common as c
from kubed.kustomize.grafana import panel

QUERY = {"kind": "DataQuery", "group": "prometheus", "version": "v0", "datasource": {"name": "prom"},
         "spec": {"expr": "up"}}
SPEC = {"title": "Memory",
        "data": {"kind": "QueryGroup", "spec": {"queries": [{"kind": "PanelQuery", "spec": {"refId": "A", "query": QUERY}}]}},
        "vizConfig": {"kind": "VizConfig", "group": "timeseries", "spec": {"options": {}}}}


def cfg(spec, name="memory"):
  return {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "kind": "Panel",
          "metadata": {"name": name, "labels": {"app": "redis"},
                       "annotations": {"config.kubernetes.io/function": "exec:\n  path: kubectl-kubed\n"}},
          "spec": spec}


def run(konfig, items):
  return panel.transform(c.new_resource_list_object(konfig, items))["items"]


def test_a_plain_panel_becomes_a_resolved_local_panel():
  konfig = cfg(SPEC)
  out = run(konfig, [copy.deepcopy(konfig)])  # generator mode passes the config in items
  assert len(out) == 1
  p = out[0]
  assert (p["kind"], p["metadata"]["name"], p["metadata"]["labels"]) == ("Panel", "memory", {"app": "redis"})
  assert p["metadata"]["annotations"] == {"config.kubernetes.io/local-config": "true",
                                          "grafana.krm.kubed.io/resolved": "true"}
  assert p["spec"] == SPEC


def test_a_library_panel_becomes_a_grafanalibrarypanel():
  lp = run(cfg({**SPEC, "library": {"folder": "apps"}}), [])[0]
  assert lp["kind"] == "GrafanaLibraryPanel"
  assert (lp["spec"]["uid"], lp["spec"]["folderUID"]) == ("memory", "apps")
  model = json.loads(lp["spec"]["json"])
  assert (model["uid"], model["name"], model["type"]) == ("memory", "Memory", "timeseries")
  assert "library" not in model


def test_library_name_overrides_the_title():
  lp = run(cfg({**SPEC, "library": {"name": "Redis memory"}}), [])[0]
  assert json.loads(lp["spec"]["json"])["name"] == "Redis memory"


def test_transformer_mode_reads_queries_from_the_list_and_keeps_other_items():
  dq = {"apiVersion": "grafana.krm.kubed.io/v1alpha1", "metadata": {"name": "mem", "labels": {"p": "m"}}, **QUERY}
  spec = {**SPEC, "data": {"kind": "QueryGroup", "spec": {"queries": [
    {"kind": "Target", "spec": {"kind": "DataQuery", "matchLabels": {"p": "m"}}}]}}}
  out = run(cfg(spec), [dq])
  assert out[0] == dq
  assert out[1]["spec"]["data"]["spec"]["queries"] == [
    {"kind": "PanelQuery", "spec": {"refId": "mem", "hidden": False, "query": QUERY}}]
