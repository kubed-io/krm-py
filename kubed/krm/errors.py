import sys


class KubedError(Exception):
  """Base class for known errors raised by this project.

  Anything that subclasses ``KubedError`` is an intentional, well-formed
  failure surface — the top-level executor catches it and renders its
  message verbatim via ``plugin_fail``. Anything not in this hierarchy is
  treated as unhandled.
  """


class FieldPathNotFound(KubedError, LookupError):
  """A JSON-pointer-style field path did not resolve on a resource."""


def plugin_fail(message):
  print(message, file=sys.stderr)
  sys.exit(1)


class EmbedError(KubedError):
  """An Embed node could not be resolved to the file it names."""


class TargetError(KubedError):
  """A Target node matched the wrong number of resources."""


class ElementNotFound(KubedError):
  """A dashboard layout references an element that nothing provides."""


class ConversionError(KubedError):
  """A v2 panel could not be converted to the v1 panel model."""
