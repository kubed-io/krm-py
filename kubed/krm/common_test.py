
import pytest
from kubed.krm import common as c
from kubed.krm.model import ResourceList, KObject
import yaml

def test_get_konfig():
    konfig = c.konfig("lastpass")
    assert "secretClass" in konfig
    sc = konfig["secretClass"]
    assert sc[0]["name"] == "note"

def test_res_class():
    konfig = KObject(
        "krm.kubed.io",
        "Test",
        "foo"
    )
    items = [{
        "apiVersion": "foo",
        "kind": "Bar"
    },{
        "apiVersion": "bar",
        "kind": "Foo"
    }]
    res = ResourceList(konfig, items)
    # print(res)
    # c.dump(res)
    # for r in res:
    #     print(r["kind"])