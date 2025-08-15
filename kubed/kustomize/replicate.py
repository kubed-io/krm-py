from kubed.krm import common as c
import copy

def transform(krm: dict) -> dict:
  """Replicate Specified Items
  
  For each of the `items` specified, replicate the resource. For each of the iterations of the items,
  the resource will get a series of patches to differentiate each one. This can either target a number 
  of resources in the items, or specify a template to use as a generator. 

  Args:
    krm: The KRM ResourceList to have items replicated. 

  Returns:
    What came in but with the target/template transformed to kind List with each item a replicate from the transformation. 
  """
  konfig = krm["functionConfig"]
  if "template" in konfig["spec"]:
    krm["items"].append(replicate(konfig, konfig["spec"]["template"]))
  else:
    t = konfig["spec"].get("target", {})
    krm["items"] = [replicate(konfig, r) if c.targeted(r, t) else r for r in krm["items"]]
  return krm

def replicate(konfig, res):
  """Replicate a Resource N Times
  
  Based on a list of items to iterate over, the resource(res) will be copided as many 
  times as there are items in the list. If the config specifies a `replicas` field,
  then there will be that many of the res copied. 

  Args:
    konfig: The KRM Configuration for a replication transformation
    res: An arbitrary Kubernetes manifest to be copied many times

  Returns:
    A kind List with as many items as should be replicated. Kustomize will expand the list in to the terminal. 
  """
  c.mergeMeta(res, konfig)
  spec = konfig["spec"]
  itemsLen = len(spec["items"])
  if "replicas" not in spec:
    spec["replicas"] = itemsLen
  status = {
    "iter": 1,
    "idx": 0
  }
  # ttlIter = 1 # total amount of iterations through the item list
  # itemIdx = 0 # the index of the current item for the iteration
  outItems = []
  baseName = res["metadata"].get("name", "")
  # iterate for the amount of replicas
  for i in range(spec["replicas"]):
    status["i"] = i
    # resetting item index  allows for more replicas than the count of items
    if status["idx"] >= itemsLen:
      # itemIdx = 0
      # ttlIter += 1
      status["idx"] = 0
      status["iter"] += 1 # the count of how many times we have gone over the items
    
    # get the current item and a copy of the resource
    item = spec["items"][status["idx"]]
    rep = copy.deepcopy(res)

    # the overrides make the differences between the replicas
    for ov in spec["overrides"]:
      if "target" not in ov or c.targeted(rep, ov["target"]):
        patches = [process_patch(patch, item, rep, status) for patch in ov["patches"]]
        rep = c.apply_patches(rep, patches)
    outItems.append(rep)
    # inc the iteration
    status["idx"] += 1
  return c.new_list_object(baseName, outItems)

def process_patch(patch, item, rep, status):
  cpPatch = copy.deepcopy(patch)

  # resolve template value only if there is a string value key
  if "value" in patch and type(patch["value"]) == str:
      if patch["op"] == "add":
        cpPatch["value"] = patch["value"].format(status=status, item=item)
      elif patch["op"] == "replace":
        v = c.deepGet(rep, patch["path"])
        cpPatch["value"] = patch["value"].format(v, status=status, item=item)
  return cpPatch

def op_merge_resolve(patch, item):
  if "valueFrom" in patch:
    vf = patch["valueFrom"]
    if "itemKey" in vf:
      patch["value"] = item[vf["itemKey"]]
  return {
    "op": "replace",
    "path": patch["path"],
    "value": patch["value"]
  }

