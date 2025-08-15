import sys

def plugin_fail(message):
  print(message, file=sys.stderr)
  sys.exit(1)