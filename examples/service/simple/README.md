# Simple Service Example - Embedded Source

Demonstrates embedded source code directly in service.yaml.

## Use Case

Perfect for:
- Single-file functions
- Quick prototypes
- Learning the Service pattern
- Functions with no external dependencies

## What This Example Shows

**Embedded Source (`type: literal`)**:
- Code embedded directly in YAML
- No separate Python files needed
- Automatically saved as `main.py` in package
- No `kubectl fn publish` needed - just deploy

## File Structure

```
simple/
├── service.yaml        # Contains embedded Python code
├── kustomization.yaml
└── README.md
```

Notice: **No main.py file!** The Python code lives in service.yaml.

## Deploy

```bash
cd examples/service/simple
kubectl up .
```

That's it! No publish step needed since source is embedded.

## Test

```bash
curl http://router.flow/hello/greet
curl "http://router.flow/hello/greet?name=Kelly"
```

## Generated Resources

- 1 Package (`hello`) with embedded main.py
- 1 Function (`hello-greet`)
- 1 HTTPTrigger (`GET /hello/greet`)

Total: 3 resources

## Key Feature: Embedded Source

```yaml
spec:
  package:
    source:
      type: literal  # Embedded instead of url
      literal: |
        from flask import request, jsonify

        def greet():
            name = request.args.get('name', 'World')
            return jsonify({"message": f"Hello, {name}!"})
```

- Type is `literal` (not `url`)
- Python code goes in `literal` field
- Saved as `main.py` in the package
- No GCS bucket needed
