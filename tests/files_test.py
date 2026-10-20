from kubed.krm import files as f


def test_bare_equals_is_a_string():
  # kustomize unquotes '=' (a Cloud Monitoring filter operator); SafeLoader alone refuses it
  assert f.load("filters:\n- metric.type\n- =\n- x\nop: =\n") == {"filters": ["metric.type", "=", "x"], "op": "="}


def test_other_implicit_types_still_resolve():
  assert f.load("n: 1\nb: true\nz: null\nd: 2026-10-20\n")["n"] == 1
  assert list(f.load_all("a: =\n---\nb: 2\n")) == [{"a": "="}, {"b": 2}]
