from kubernetes import config, dynamic
from kubernetes.client import api_client
import os

def getClient():
    return dynamic.DynamicClient(
        api_client.ApiClient(
            configuration=config.load_incluster_config() if os.environ.get("CROSSHOOK_ENV") == "cluster" else config.load_kube_config()
        )
    )
