import pytest
from kubed.krm import common as c, files as f

def test_replicate_as_generator():
  konfig = f.load_yaml("examples/replicate/generated.yaml")
  res = c.resolve(
    c.new_resource_list_object(konfig)
  )
  assert konfig["apiVersion"] == "krm.kubed.io"
  # because kind List should be the only one
  assert len(res["items"]) == 1
  r = res["items"][0]
  assert r["kind"] == "List"
  # the list should have two items though
  assert len(r["items"]) == 2
  # the first one should be
  assert r["items"][0] == {
    'apiVersion': 'v1', 
    'kind': 'Service', 
    'metadata': {
      'labels': {
        'pizza.kind/stuffed': 'pineapple-foo',
        'stuff.junk/garbage': 'stinky'
      }, 
      'name': 'domain-replicas-foo', 
      'namespace': 'mastery'
    }, 
    'spec': {
      'type': 'ExternalName', 
      'externalName': 'google.com'
    }
  }

def test_running_with_target():
  konfig = f.load_yaml("examples/replicate/multiply.yaml")
  items = f.load_yaml("examples/replicate/some-app.yaml", True)
  res = c.resolve(
    c.new_resource_list_object(konfig, items)
  )
  # print(f.parse_to(res))
  # should be three b/c deployment becomes a list and service and pod are untouched
  assert len(res["items"]) == 3
  # the kinds in the list are as follows
  assert res["items"][0]["kind"] == "Pod"
  assert res["items"][1]["kind"] == "Service"
  assert res["items"][2]["kind"] == "List" # b/c Deployment was replicated

  # the example stated there should be specifically three deployments in the list
  l = res["items"][2]
  assert len(l["items"]) == 3
