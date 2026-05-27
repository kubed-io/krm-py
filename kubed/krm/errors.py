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
