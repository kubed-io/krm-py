"""Folder: a Grafana folder that places the dashboards, library panels and folders it selects.

Runs under transformers:, after Dashboard, so every emitted CR is in the list. The
target is matched against each CR as the kind it was written as (Dashboard, Panel,
Folder), from its grafana.krm.kubed.io/kind annotation.
"""
from kubed.krm import common as c
from kubed.kustomize.grafana import crs

AUTHORING = "grafana.krm.kubed.io/v1alpha1"


def transform(krm: dict) -> dict:
  konfig = krm["functionConfig"]
  uid = konfig["metadata"]["name"]
  target = konfig["spec"].get("target")
  if target:
    for i in krm["items"]:
      kind = i.get("metadata", {}).get("annotations", {}).get(crs.KIND)
      if not kind or not c.targeted({**i, "apiVersion": AUTHORING, "kind": kind}, target):
        continue
      current = crs.folder_of(i)
      if current:
        c.add_result(krm, f"folder {uid}: {kind} {i['metadata']['name']} is already in folder {current}; left there",
                     "warning", i)
        continue
      crs.place(i, uid)
  krm["items"] = krm["items"] + [crs.folder_cr(konfig)]
  return krm
