# Extending  

In this tutorial we will make a brand new plugin called LabelMe. 

## Step 1: Start Project  

We start by ... 

```py
from kubed.krm import common as c

def transform(krm):
  konfig = krm["functionConfig"] # the krm yaml which triggers the function
  # ... do kustom transforms to krm["items"]
  return krm
c.execute(transform)
```

## JsonSchema  

```{jsonschema} ../schema.json
```