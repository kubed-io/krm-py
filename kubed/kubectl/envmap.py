from kubed.krm import common as c, k8s
from cachetools import cached, TTLCache
import base64
import re
from kubernetes.dynamic.exceptions import NotFoundError

client = k8s.getClient()

def setenv():
    envmap = {}
    res = c.krm_init()
    conf = res["functionConfig"]
    ns = conf["metadata"].get("namespace", "default")

    # merge each referenced configmap or secret
    for envfrom in conf.get("envFrom",[]):
        envmap.update(get_env_from_ref(envfrom, ns))

    # resolve each var reference and replace and variables
    for env in conf.get("env",[]):
        k,v = get_variable(env, ns)
        envmap[k] = replace_vars(v, envmap)

    # print the .env content
    print(env_printout(envmap)) 


def replace_vars(v, envmap):
    """Replace Variables in Values  

    Uses a dictionary of variables to replace string tokens.
    """
    for k in keys_from_string(v):
        v = v.replace(f"$({k})", envmap[k])
    return v

def keys_from_string(v):
    """Finds Var Keys in a string
    
    The variables in the string are the same as kubernetes pod 
    variables using parentheses. This function finds a unique 
    list of these variables.  
    """
    return list(dict.fromkeys(re.findall('\$\((.*?)\)', v)))

def env_printout(envmap):
    env_list = [f"{k}={v}" for k, v in envmap.items()]
    return "\n".join(env_list)

def decode_value(v):
    return base64.b64decode(v).decode("utf-8")

def get_variable(env, ns):
    if "value" in env:
        v = env["value"]
    elif "valueFrom" in env:
        if "secretKeyRef" in env["valueFrom"]:
            ref = env["valueFrom"]["secretKeyRef"]
            o = get_reference("Secret", ref["name"], ns)
            v = decode_value(o["data"][ref["key"]])
        elif "configMapKeyRef" in env["valueFrom"]:
            ref = env["valueFrom"]["configMapKeyRef"]
            o = get_reference("ConfigMap", ref["name"], ns)
            v = o["data"][ref["key"]]
    return (env['name'], v)

def get_env_from_ref(envFrom, ns):
    if "secretRef" in envFrom:
        kind = "Secret"
        ref = envFrom["secretRef"]
        decode = True
    elif "configMapRef" in envFrom:
        kind = "ConfigMap"
        ref = envFrom["configMapRef"]
        decode = False
    try:
        o = get_reference(kind, ref["name"], ns)
    except NotFoundError:
        print("Not found")
    d = o["data"]
    if decode:
        d = {k: decode_value(v) for (k,v) in d.items()}
    return d

@cached(cache=TTLCache(maxsize=1024,ttl=10))
def get_reference(kind, name, namespace):
    return client.resources.get(
        api_version="v1", kind=kind
    ).get(
        name=name,
        namespace=namespace
    )
