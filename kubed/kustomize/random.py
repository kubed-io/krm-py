"""Random KRM Transformer

Generates a random value and writes it into matched target resource fields.
When ``keepers`` are configured, the value is deterministically derived from
the keeper field values so the same inputs always produce the same output.
This is the same idea as Terraform's ``random_string`` / ``random_id``
keepers attribute, adapted to KRM.

See: https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string
"""

import copy
import json
import random
import string

from kubed.krm import common as c


DEFAULT_LENGTH = 8
DEFAULT_SPECIAL = "!@#$%&*()-_=+[]{}<>:?"

# Resources can opt in to being a keeper by declaring which of their own
# fieldPaths matter. Inverted control: the random.yaml selector just needs
# to match the resource; the resource brings its own list of paths along.
KEEPER_FIELDPATHS_ANNOTATION = "random.krm.kubed.io/keepers.fieldpaths"



def transform(krm: dict) -> dict:
  """Random Transformer

  Resolves keeper values from the input items, generates a random value, then
  writes that value into each item that matches one of the configured targets.

  Args:
    krm: The KRM ResourceList with the Random functionConfig.

  Returns:
    The transformed ResourceList with the random value patched into targets.
  """
  spec = krm["functionConfig"]["spec"]
  seed = resolve_keepers(krm)
  value = generate(spec, seed)
  krm["items"] = [apply_targets(spec, r, value) for r in krm["items"]]
  return krm


def resolve_keepers(krm: dict):
  """Resolve Keeper Values to a Seed

  Walks each keeper, collects values from every matched item, and joins them
  into a single string. That string seeds the RNG so the same set of keeper
  values always yields the same random value. Returns ``None`` when no
  keepers are configured, meaning the output should be non-deterministic.

  Each keeper is a resource selector (``kind``/``name``/``matchLabels``/etc.)
  plus an optional list of ``fieldPaths``. Per matched resource, paths are
  resolved by fallback:

  1. **Keeper-declared** ``fieldPaths`` on the selector — wins if present.
  2. **Resource-declared** via the
     ``random.krm.kubed.io/keepers.fieldpaths`` annotation (newline-separated
     list). Lets a component opt its own resource into the seed without the
     random.yaml needing to enumerate paths.
  3. **Whole resource** — used when neither list is present.
     ``metadata.annotations`` is stripped so annotation churn doesn't
     re-roll.

  When a matched resource carries the annotation AND the keeper also has
  explicit ``fieldPaths``, a structured ``warning`` is appended to
  ``krm.results`` noting that the explicit paths win.

  Each value — scalar, nested object, or large string — is canonicalized to
  a stable string. When a selector matches multiple resources, they're
  sorted by ``kind/namespace/name`` so the seed doesn't depend on items
  order.

  Args:
    krm: The KRM ResourceList. Reads keepers from
      ``krm.functionConfig.spec.keepers``, items from ``krm.items``, and
      appends any warnings to ``krm.results``.

  Returns:
    A seed string built from keeper values, or ``None`` for no keepers.
  """
  keepers = krm["functionConfig"]["spec"].get("keepers", [])
  if not keepers:
    return None
  items = krm["items"]
  parts = []
  for k in keepers:
    keeper_paths = k.get("fieldPaths") or []
    matches = sorted(
      (r for r in items if c.targeted(r, k)),
      key=_resource_sort_key,
    )
    for r in matches:
      annotation_paths = _annotation_fieldpaths(r)
      if keeper_paths and annotation_paths:
        c.add_result(
          krm,
          "keeper fieldPaths take precedence over the {ann} annotation "
          "on this resource".format(ann=KEEPER_FIELDPATHS_ANNOTATION),
          severity="warning",
          resource=r,
        )
      paths = keeper_paths or annotation_paths
      if not paths:
        parts.append(_canonicalize(r))
        continue
      for fp in paths:
        parts.append(_canonicalize(c.deepGet(r, fp)))
  return "|".join(parts)


def _annotation_fieldpaths(res: dict) -> list:
  """Read fieldPaths the resource itself declares via the keepers annotation."""
  raw = (res.get("metadata", {}).get("annotations") or {}).get(
    KEEPER_FIELDPATHS_ANNOTATION
  )
  if not raw:
    return []
  return [line.strip() for line in raw.splitlines() if line.strip()]


def _canonicalize(v) -> str:
  """Canonical string for any keeper value — scalars, objects, whole resources.

  JSON-dump with sorted keys (``default=str`` covers anything non-JSON-native),
  so structurally equivalent dicts produce identical output regardless of
  insertion order. If the value looks like a Kubernetes resource — a dict
  with a ``metadata.annotations`` object — annotations are dropped first,
  since annotation churn from kustomize/ESO/controllers is noise we never
  want to re-roll on.
  """
  if (isinstance(v, dict)
      and isinstance(v.get("metadata"), dict)
      and isinstance(v["metadata"].get("annotations"), dict)):
    v = copy.deepcopy(v)
    v["metadata"].pop("annotations", None)
  return json.dumps(v, sort_keys=True, separators=(",", ":"), default=str)


def _resource_sort_key(r: dict) -> tuple:
  meta = r.get("metadata", {})
  return (r.get("kind", ""), meta.get("namespace", ""), meta.get("name", ""))


def generate(spec: dict, seed):
  """Generate the Random Value

  Honors a Terraform-like option set: ``length``, ``lower``, ``upper``,
  ``numeric``, ``special``, and ``override_special`` for strings; ``min`` and
  ``max`` for numbers. A non-``None`` seed makes the result idempotent.

  Args:
    spec: The Random function spec.
    seed: The seed string from keepers, or ``None`` for true randomness.

  Returns:
    A random string or integer based on ``spec.type``.
  """
  rng = random.Random(seed)

  if spec.get("type", "string") == "number":
    return rng.randint(spec.get("min", 0), spec.get("max", 999999))

  pool = ""
  if spec.get("lower", True):
    pool += string.ascii_lowercase
  if spec.get("upper", True):
    pool += string.ascii_uppercase
  if spec.get("numeric", True):
    pool += string.digits
  if spec.get("special", False):
    pool += spec.get("override_special", DEFAULT_SPECIAL)

  length = spec.get("length", DEFAULT_LENGTH)
  return "".join(rng.choice(pool) for _ in range(length))


def apply_targets(spec: dict, res: dict, value) -> dict:
  """Apply the value to each matching target on a single resource."""
  for t in spec.get("targets", []):
    if c.targeted(res, t):
      res = patch_value(res, t, value)
  return res


def patch_value(res: dict, target: dict, value) -> dict:
  """Patch the Random Value into One Field

  Writes the value at ``target.fieldPath``. When ``options.delimiter`` is set,
  the existing field is split on that delimiter and the slot at
  ``options.index`` is replaced with the value — useful for placing the
  random token into part of a name like ``my-job-<random>``.

  Args:
    res: The resource to patch.
    target: A target selector with ``fieldPath`` and optional ``options``.
    value: The generated random value.

  Returns:
    The patched resource.
  """
  fieldPath = target["fieldPath"]
  options = target.get("options", {})

  if "delimiter" in options:
    delim = options["delimiter"]
    idx = options.get("index", 0)
    current = c.deepGet(res, fieldPath, default="")
    parts = str(current).split(delim) if current else []
    while len(parts) <= idx:
      parts.append("")
    parts[idx] = str(value)
    final = delim.join(parts)
  else:
    final = value

  return c.apply_patches(res, [{
    "op": "add",
    "path": fieldPath,
    "value": final
  }])
