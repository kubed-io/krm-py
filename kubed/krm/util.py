import re

def missing_key_list(obj, desired_keys):
    """Find Missing Desired Keys
    
    Discovers the missing keys from an object based
    on an array of keys which should be present.  
    """
    return set(desired_keys) - set(obj.keys())

def prefix_copy(o, p):
    """Copy Prefixed Keys

    Copies a subset of keys from an object based on a prefix. 
    The prefix is stripped from the resulting keys. 

    Args:
        o (dictionary): Each key has some defining prefix to choose the desired keys. 
        p (string): The prefix on the key to.   
    """
    return dict([(k.removeprefix(p), v) for k, v in o.items() if re.match(f"{p}*", k)])