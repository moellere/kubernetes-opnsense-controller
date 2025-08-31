import os
import logging
import yaml
import threading
import time
from dotenv import load_dotenv
from kubernetes import client, config, watch
from src.clients.opnsense import from_env as opnsense_from_env
from src.plugins.metallb import MetalLBPlugin
from src.plugins.haproxy_declarative import HAProxyDeclarativePlugin
from src.plugins.haproxy_ingress_proxy import HAProxyIngressProxyPlugin
from src.plugins.dns_services import DNSServicesPlugin
from src.plugins.dns_ingresses import DNSIngressesPlugin
from src.plugins.dns_haproxy_ingress_proxy import DNSHAProxyIngressProxyPlugin
from .version import __version__ 

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

# --- Helper Functions ---
def get_controller_config(k8s_core_v1_api):
    """
    Fetches and parses the controller's ConfigMap from the cluster.
    """
    namespace = os.getenv('CONTROLLER_NAMESPACE', 'kube-system')
    name = os.getenv('CONTROLLER_CONFIGMAP', 'kubernetes-opnsense-controller')
    logging.info(f"Attempting to load configuration from ConfigMap: {namespace}/{name}")

    try:
        cm = k8s_core_v1_api.read_namespaced_config_map(name, namespace)
        config_yaml = cm.data.get('config')
        if not config_yaml:
            logging.error(f"ConfigMap '{name}' does not have a 'config' key.")
            return None

        return yaml.safe_load(config_yaml)

    except client.ApiException as e:
        if e.status == 404:
            logging.error(f"ConfigMap '{name}' not found in namespace '{namespace}'.")
        else:
            logging.error(f"Error reading ConfigMap: {e}")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Error parsing ConfigMap YAML: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading config: {e}")
        return None

# --- Watcher Threads ---
def watch_resources(resource_func, plugins):
    w = watch.Watch()
    resource_type = resource_func._apis['list_node'].__name__.split('_')[1]
    logging.info(f"Starting to watch for {resource_type} events...")
    for event in w.stream(resource_func):
        logging.info(f"Event: {event['type']} on {resource_type}")
        for plugin in plugins:
            plugin.run()

# --- Initialization ---
def main():
    logging.info("Starting Kubernetes OPNsense Controller {__version__}")

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    k8s_core_v1 = client.CoreV1Api()
    k8s_networking_v1 = client.NetworkingV1Api()

    try:
        opnsense_client = opnsense_from_env()
        logging.info("OPNsense client initialized.")
    except ValueError as e:
        logging.error(f"Failed to initialize OPNsense client: {e}")
        return

    controller_config = get_controller_config(k8s_core_v1)
    if not controller_config:
        logging.error("Could not load controller configuration. Exiting.")
        return

    # --- Plugin Loading ---
    plugins = []
    watch_map = {}

    def register_plugin(plugin_class, k8s_api, config, resource_types, extra_args=None):
        if extra_args is None:
            extra_args = {}
        p = plugin_class(k8s_api, opnsense_client, config, **extra_args)
        plugins.append(p)
        for r_type in resource_types:
            if r_type not in watch_map:
                watch_map[r_type] = []
            watch_map[r_type].append(p)

    if controller_config.get('metallb', {}).get('enabled', False):
        register_plugin(MetalLBPlugin, k8s_core_v1, controller_config['metallb'], ['node'])

    if controller_config.get('haproxy-declarative', {}).get('enabled', False):
        register_plugin(HAProxyDeclarativePlugin, k8s_core_v1, controller_config['haproxy-declarative'], ['config_map'])

    if controller_config.get('haproxy-ingress-proxy', {}).get('enabled', False):
        register_plugin(HAProxyIngressProxyPlugin, k8s_networking_v1, controller_config['haproxy-ingress-proxy'], ['ingress'])

    if controller_config.get('opnsense-dns-services', {}).get('enabled', False):
        register_plugin(DNSServicesPlugin, k8s_core_v1, controller_config['opnsense-dns-services'], ['service'])

    if controller_config.get('opnsense-dns-ingresses', {}).get('enabled', False):
        register_plugin(DNSIngressesPlugin, k8s_networking_v1, controller_config['opnsense-dns-ingresses'], ['ingress'])

    if controller_config.get('opnsense-dns-haproxy-ingress-proxy', {}).get('enabled', False):
        haproxy_ingress_config = controller_config.get('haproxy-ingress-proxy', {})
        register_plugin(DNSHAProxyIngressProxyPlugin, k8s_networking_v1, controller_config['opnsense-dns-haproxy-ingress-proxy'], ['ingress'], extra_args={'haproxy_ingress_proxy_config': haproxy_ingress_config})

    # --- Initial Reconciliation ---
    logging.info("Performing initial reconciliation for all plugins...")
    for plugin in plugins:
        plugin.run()

    # --- Main Controller Loop ---
    resource_map = {
        'node': k8s_core_v1.list_node,
        'config_map': k8s_core_v1.list_config_map_for_all_namespaces,
        'ingress': k8s_networking_v1.list_ingress_for_all_namespaces,
        'service': k8s_core_v1.list_service_for_all_namespaces
    }

    threads = []
    for resource_type, plugin_list in watch_map.items():
        if resource_type in resource_map:
            thread = threading.Thread(target=watch_resources, args=(resource_map[resource_type], plugin_list))
            threads.append(thread)

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("Shutting down controller...")

    logging.info("Controller shut down.")

if __name__ == '__main__':
    main()
