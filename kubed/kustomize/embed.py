from kubed.krm import common as c, files as f

def transform(krm: dict) -> dict:
  """Embed Transformer
  
  The entrypoint for the KRM function to execute the 'embed file' transformation. 
  The config can use the 'template' key to run as a generator, or specify the 
  'target' key to embed the files content into any matching resources.  

  Args:
    krm: KRM ResourceList input with the embed functions configuration. 

  Returns:
    The transformed input with the contents of a file embedded into at least one of the items. 
  """
  konfig = krm["functionConfig"]
  if "template" in konfig["spec"]:
    krm["items"].append(embed(konfig, konfig["spec"]["template"]))
  else:
    t = konfig["spec"].get("target", {})
    krm["items"] = [embed(konfig, r) if c.targeted(r, t) else r for r in krm["items"]]
  return krm

# Using the given config, a file will be embeded into the target
def embed(konfig: dict, res: dict) -> dict:
  """Embed File in Resource
  
  Embeds a file of choice into the given resource. The config describes where
  in the object to place the contents of the file. This is the actual logic of
  the transformation. 

  Args:
    config: The krm config resource for the embed function. 
    res: The Kubernetes Resource of choice to embed the file into. 

  Returns:
    The resource from the input is returned with the embedded file contents. 
  """
  spec = konfig["spec"]
  contents = f.get_file_contents(spec["file"])
  fileType = spec["fileType"] if "fileType" in spec else f.discover_file_type(spec["file"])

  # nested means the file will be embedded as yaml into yaml
  if ("nested" in spec and spec["nested"]):
    contents = f.parse_from(contents, fileType)

  # this will embed the file contents as the desired mime type
  elif ("parse" in spec):
    obj = f.parse_from(contents, fileType)
    contents = f.parse_to(obj, spec["parse"])

  # apply the final patch to the resource
  return c.apply_patches(res, [{
    "op": "add",
    "path": spec["target"]["fieldPath"],
    "value": contents
  }])
