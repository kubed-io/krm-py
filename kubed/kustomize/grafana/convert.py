"""A v2 panel element spec as the v1 panel model, the way Grafana converts it.

Library panels exist only in the v1 model on Grafana 13.2.1, so a library Panel is
written in v2 and converted here. The rules reproduce Grafana's own v2→v1 conversion;
tests/grafana_convert_test.py checks them panel by panel against it.
"""
import json
from kubed.krm.errors import ConversionError

QUERY_OPTIONS = ("maxDataPoints", "interval", "timeFrom", "timeShift", "cacheTimeout", "queryCachingTTL",
                 "hideTimeOverride")


def to_v1(spec: dict, name: str = "") -> dict:
  """The v1 panel model for a v2 panel element's spec, without id and gridPos."""
  viz = spec.get("vizConfig") or {}
  if not viz.get("group"):
    raise ConversionError(f"panel {name}: vizConfig.group is required, it becomes the v1 panel type")
  data = (spec.get("data") or {}).get("spec") or {}
  out = {"type": viz["group"], "title": spec.get("title", "")}
  if "version" in viz:
    out["pluginVersion"] = viz["version"]
  for k in ("description", "links"):
    if spec.get(k):
      out[k] = spec[k]
  if spec.get("transparent"):
    out["transparent"] = True
  vs = viz.get("spec") or {}
  field_config = {k: v for k, v in (vs.get("fieldConfig") or {}).items() if v not in ({}, [])}
  if field_config:
    out["fieldConfig"] = field_config
  if "options" in vs:
    out["options"] = vs["options"]
  out["targets"] = [_target(q) for q in data.get("queries", [])]
  shared = {json.dumps(t.get("datasource"), sort_keys=True) for t in out["targets"]}
  if out["targets"] and len(shared) == 1 and "datasource" in out["targets"][0]:
    out["datasource"] = out["targets"][0]["datasource"]
  transformations = [_transformation(t, name) for t in data.get("transformations", [])]
  if transformations:
    out["transformations"] = transformations
  options = data.get("queryOptions") or {}
  for k in QUERY_OPTIONS:
    if k in options:
      out[k] = options[k]
  return out


def _target(panel_query):
  s = panel_query["spec"]
  q = s.get("query") or {}
  t = {}
  ds = {}
  if q.get("group"):
    ds["type"] = q["group"]
  if (q.get("datasource") or {}).get("name"):
    ds["uid"] = q["datasource"]["name"]
  if ds:
    t["datasource"] = ds
  t.update(q.get("spec") or {})
  t["refId"] = s["refId"]
  if s.get("hidden"):
    t["hide"] = True
  return t


def _transformation(t, name):
  if t.get("kind") != "Transformation" or not t.get("group"):
    raise ConversionError(f"panel {name}: transformation {json.dumps(t)} is not a v2 Transformation")
  return {"id": t["group"], **(t.get("spec") or {})}
