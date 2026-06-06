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
        patches = [process_patch(patch, item, rep) for patch in ov["patches"]]
        rep = c.apply_patches(rep, patches)
    outItems.append(rep)
    # inc the iteration
    status["idx"] += 1
  return c.new_list_object(baseName, outItems)

def process_patch(patch, item, rep):
  """Resolve one override into a plain JSON Patch op.

  - `valueFrom: {path: <jmespath>}` reads that value off the current `item`
    (`common.search`) — copies any type (e.g. a members list); `@` is the whole
    item. The object form (k8s `valueFrom` convention) leaves room for more
    source types later.
  - `options` (when present) combines the read value with the field's current
    value via `common.value_from`, by `strategy` (default `splice`):
    `{delimiter, index}` splices into a segment (replace-at-index, shared with the
    random transformer); `{strategy: merge}` flat-merges over the current value
    (keeps keys like spec.baseDn); `{strategy: replace}` overwrites. With no
    `options`, the read value is used as-is.
  JSON-pointer to *read* (the item) and *write* (the resource via jsonpatch). A
  patch with a literal `value` (no valueFrom) passes through; `options` applies
  to either.

  Args:
    patch: A single override patch (op/path + value/valueFrom/options).
    item: The current item from spec.items the value is read from.
    rep: The replica being built (source of the field's current value).

  Returns:
    A copy of the patch with valueFrom/options resolved into a concrete value.
  """
  cpPatch = copy.deepcopy(patch)
  vf = patch.get("valueFrom")
  if vf is not None:
    current = c.deepGet(rep, patch["path"], default="")   # the value already at the target
    cpPatch["value"] = copy.deepcopy(c.value_from(vf, patch.get("options"), item, current))
  cpPatch.pop("valueFrom", None)
  cpPatch.pop("options", None)
  return cpPatch

