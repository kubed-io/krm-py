"""Random KRM Transformer

Generates a random value and writes it into matched target resource fields.
When ``keepers`` are configured, the value is deterministically derived from
the keeper field values so the same inputs always produce the same output.
This is the same idea as Terraform's ``random_string`` / ``random_id``
keepers attribute, adapted to KRM.

See: https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string
"""

import random
import string

from kubed.krm import common as c


DEFAULT_LENGTH = 8
DEFAULT_SPECIAL = "!@#$%&*()-_=+[]{}<>:?"


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
  seed = resolve_keepers(spec.get("keepers", []), krm["items"])
  value = generate(spec, seed)
  krm["items"] = [apply_targets(spec, r, value) for r in krm["items"]]
  return krm


def resolve_keepers(keepers: list, items: list):
  """Resolve Keeper Values to a Seed

  Walks each keeper target, looks up the field value on every matched item,
  and joins them into a single string. That string seeds the RNG so the same
  set of keeper values always yields the same random value. Returns ``None``
  when no keepers are configured, meaning the output should be non-deterministic.

  Args:
    keepers: List of target selectors with a ``fieldPath`` to read.
    items: The KRM items to read keeper values from.

  Returns:
    A seed string built from keeper values, or ``None`` for no keepers.
  """
  if not keepers:
    return None
  parts = []
  for k in keepers:
    for r in items:
      if c.targeted(r, k):
        parts.append(str(c.deepGet(r, k["fieldPath"], default="")))
  return "|".join(parts)


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
