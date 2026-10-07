import os
import shutil
import subprocess
import sys
import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("kustomize") is None, reason="needs kustomize")
def test_the_example_builds_to_expected(tmp_path):
  # kustomize finds `kubectl-kubed` on PATH; this one runs the checkout, not whatever is installed
  wrapper = tmp_path / "kubectl-kubed"
  wrapper.write_text("#!/bin/sh\n"
                     f"PYTHONPATH={os.pathsep.join([ROOT, *sys.path])} exec {sys.executable} "
                     "-c 'from kubed.krm.common import execute; execute()' \"$@\"\n")
  wrapper.chmod(0o755)
  env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}
  built = subprocess.run(["kustomize", "build", "--enable-alpha-plugins", "--enable-exec", "examples/grafana"],
                         cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout
  with open(os.path.join(ROOT, "examples", "grafana", "expected.yaml")) as fh:
    assert list(yaml.safe_load_all(built)) == list(yaml.safe_load_all(fh))
