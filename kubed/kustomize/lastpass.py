import yaml
import subprocess
import base64
import pathlib
from kubed.krm import common as c

tpl = '''
apiVersion: v1
kind: Secret
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app.kubernetes.io/created-by: kubed.lPassSecret
  annotations:
    secret/provider: lastpass
    secret/class: {secretClass}
    lastpass/id: {id}
    lastpass/name: {lname}
type: {type}
'''

specialKeys = ["username", "password", "notes", "name", "id", "url"]

def generate(krm):
    """Generate LastPass Secret
    
    Creates a Kubernetes secret based on a secret from within LastPass.
    
    Args:
        krm: The KRM ResourceList to put a secret into. 

    Returns:
        The input with a shiny new secret in the items list. 
    """
    krm["items"].append(
        lpasssecret(krm["functionConfig"]))
    return krm

def getLastpassSecretValue(id, field, encode=False):
    arg = "--{}" if field in specialKeys else '--field={}'
    p = subprocess.Popen(
        ['lpass', 'show', id, arg.format(field)], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE
    )
    out, err = p.communicate()
    return base64.b64encode(out).decode("ascii") if encode else out.decode().strip()
    # return out.decode('ascii').strip()

def lpasssecret(plugin):
    if "class" in plugin:
        konf = c.config("{}/konfig.yaml".format(pathlib.Path(__file__).parent.resolve()))
        plugin["data"] = next(filter(lambda secretClass: secretClass["name"] == plugin["class"], konf["secretClass"]))["data"]
    if "id" not in plugin:
        plugin["id"] = plugin["metadata"]["name"]
    dataKey = "data"
    encoded = True
    if "type" not in plugin:
        plugin["type"] = "Opaque"
    if plugin["type"] == "Transparent":
        plugin["type"] = "Opaque"
        dataKey = "stringData"
        encoded = False
    secret = yaml.safe_load(tpl.format(
        name=plugin["metadata"]["name"], 
        namespace=plugin["metadata"]["namespace"] if "namespace" in plugin["metadata"] else 'default',
        id=getLastpassSecretValue(plugin["id"], "id"),
        lname=plugin["id"],
        type=plugin["type"],
        secretClass=plugin["class"] if "class" in plugin else "custom"
    ))
    secret[dataKey] = {}
    if "labels" in plugin["metadata"]:
        secret["metadata"]["labels"] = {**secret["metadata"]["labels"], **plugin["metadata"]["labels"], }
    if "annotations" in plugin["metadata"]:
        secret["metadata"]["annotations"] = {**secret["metadata"]["annotations"], **plugin["metadata"]["annotations"], }
    for keyMap in plugin["data"]:
        k = keyMap["name"] if "name" in keyMap else keyMap["key"]
        secret[dataKey][k] = getLastpassSecretValue(plugin["id"], keyMap["key"], encoded)
    return secret


