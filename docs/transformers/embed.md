# Embed File Transformer  

Embeds a specified file as text into a given key of a yaml file. 

```yaml
apiVersion: krm.kubed.io
kind: Embed
```

## Module Def  

```{eval-rst}  
.. autofunction:: kustomize.embed.transform
```

```{eval-rst}  
.. autofunction:: kustomize.embed.embed
```

## Examples  

The following demonstrates some common use cases for when it is a good time to embed a file into yaml. 

```{literalinclude} ../../examples/embed/embed.yaml
:language: yaml
```
