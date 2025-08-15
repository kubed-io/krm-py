# Replication Transformer  

Takes a resource and replicates it for each of the specified items and makes changes based on patches. Transforms either a number of selected targets or generates based on a template. 

```yaml
apiVersion: krm.kubed.io
kind: Replicate
```

## Module Def  

```{eval-rst}  
.. autofunction:: kustomize.replicate.transform
```

```{eval-rst}  
.. autofunction:: kustomize.replicate.replicate
```

## Examples  

```{literalinclude} ../../examples/replicate/generated.yaml
:language: yaml
```

The Kustomization File  

```{tabbed} Tab One  
  Bumpin bro
```

```{tabbed} Tab Two  
```{panels}

```{dropdown} Nested Dropdown
:animate: fade-in

```{jinja} replicate
:file: metadata.md.jinja

---
:column: col-lg-12 p-2
```{dropdown} Hecka
  Super nice
```
