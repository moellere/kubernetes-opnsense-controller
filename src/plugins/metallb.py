import logging
from kubernetes import client

class MetalLBPlugin:
    def __init__(self, k8s_core_v1_api, opnsense_client, config):
        self.k8s_core_v1_api = k8s_core_v1_api
        self.opnsense_client = opnsense_client
        self.config = config
        self.plugin_id = 'metallb'

    def run(self):
        """
        Runs the reconciliation loop for the MetalLB plugin.
        """
        logging.info("Running MetalLB plugin reconciliation...")

        # 1. Get desired state (from Kubernetes nodes)
        desired_neighbors = self._get_desired_neighbors()
        if desired_neighbors is None:
            return # Error already logged

        # 2. Get current state (from OPNsense)
        current_neighbors = self._get_current_neighbors()
        if current_neighbors is None:
            return # Error already logged

        # 3. Reconcile states
        self._reconcile(desired_neighbors, current_neighbors)

    def _get_desired_neighbors(self):
        """
        Gets the desired BGP neighbors from Kubernetes nodes.
        """
        logging.info("Getting desired BGP neighbors from Kubernetes nodes...")
        try:
            nodes = self.k8s_core_v1_api.list_node().items
            desired = {}
            for node in nodes:
                node_ip = self._get_node_ip(node)
                if not node_ip:
                    logging.warning(f"Could not find IP for node: {node.metadata.name}")
                    continue

                host = f"kpc-{node_ip}"
                neighbor_template = self.config.get('options', {}).get(self.config['bgp-implementation'], {}).get('template', {})

                neighbor = neighbor_template.copy()
                neighbor['address'] = node_ip
                neighbor['description'] = host
                desired[host] = neighbor

            return desired
        except client.ApiException as e:
            logging.error(f"Error getting Kubernetes nodes: {e}")
            return None

    def _get_current_neighbors(self):
        """
        Gets the current BGP neighbors from OPNsense.
        """
        logging.info("Getting current BGP neighbors from OPNsense...")
        bgp_implementation = self.config.get('bgp-implementation')
        if not bgp_implementation:
            logging.error("BGP implementation not specified in config.")
            return None

        endpoint_map = {
            'openbgp': '/api/openbgpd/settings/search_neighbor',
            'frr': '/api/frr/settings/search_bgp_neighbor'
        }
        endpoint = endpoint_map.get(bgp_implementation)
        if not endpoint:
            logging.error(f"Unsupported BGP implementation: {bgp_implementation}")
            return None

        try:
            response = self.opnsense_client.get(endpoint)
            existing = {}
            if 'rows' in response:
                for row in response['rows']:
                    # Use description as the unique key, same as the PHP version
                    if 'description' in row:
                        existing[row['description']] = row
            return existing
        except Exception as e:
            logging.error(f"Error getting OPNsense neighbors: {e}")
            return None

    def _reconcile(self, desired, current):
        """
        Compares desired and current states and applies changes.
        """
        logging.info("Reconciling BGP neighbors...")
        bgp_implementation = self.config['bgp-implementation']

        to_add = {k: v for k, v in desired.items() if k not in current}
        to_update = {k: v for k, v in desired.items() if k in current and self._needs_update(current[k], v)}
        to_delete = {k: v for k, v in current.items() if k not in desired and k.startswith('kpc-')} # Only delete managed neighbors

        endpoint_map = {
            'openbgp': '/api/openbgpd/settings/',
            'frr': '/api/frr/settings/'
        }
        base_endpoint = endpoint_map[bgp_implementation]

        add_endpoint = base_endpoint + ('add_neighbor' if bgp_implementation == 'openbgp' else 'add_bgp_neighbor')
        set_endpoint = base_endpoint + ('set_neighbor' if bgp_implementation == 'openbgp' else 'set_bgp_neighbor')
        del_endpoint = base_endpoint + ('del_neighbor' if bgp_implementation == 'openbgp' else 'del_bgp_neighbor')

        # Add new neighbors
        for host, neighbor in to_add.items():
            logging.info(f"Adding neighbor: {host}")
            try:
                self.opnsense_client.post(add_endpoint, {'neighbor': neighbor})
            except Exception as e:
                logging.error(f"Failed to add neighbor {host}: {e}")

        # Update existing neighbors
        for host, neighbor in to_update.items():
            logging.info(f"Updating neighbor: {host}")
            uuid = current[host]['uuid']
            try:
                self.opnsense_client.post(f"{set_endpoint}/{uuid}", {'neighbor': neighbor})
            except Exception as e:
                logging.error(f"Failed to update neighbor {host}: {e}")

        # Delete old neighbors
        for host, neighbor in to_delete.items():
            logging.info(f"Deleting neighbor: {host}")
            uuid = neighbor['uuid']
            try:
                self.opnsense_client.post(f"{del_endpoint}/{uuid}")
            except Exception as e:
                logging.error(f"Failed to delete neighbor {host}: {e}")

        if to_add or to_update or to_delete:
            self._reload_bgp_service()

    def _needs_update(self, current, desired):
        """
        Checks if a neighbor needs to be updated.
        Compares all keys from the desired state.
        """
        for key, value in desired.items():
            if current.get(key) != value:
                return True
        return False

    def _reload_bgp_service(self):
        """
        Reloads the appropriate BGP service on OPNsense.
        """
        bgp_implementation = self.config['bgp-implementation']
        logging.info(f"Reloading {bgp_implementation} service...")

        reload_endpoint_map = {
            'openbgp': '/api/openbgpd/service/reload',
            'frr': '/api/frr/service/reload' # Assuming this is the endpoint
        }
        reload_endpoint = reload_endpoint_map.get(bgp_implementation)

        if not reload_endpoint:
            logging.error(f"No reload endpoint defined for {bgp_implementation}")
            return

        try:
            # The reload endpoint might be different, this is a guess based on the PHP code's function names
            # The PHP code calls `reloadOpenbgp()` and `reloadFrrBgp()`, which I don't have the source for.
            # This is a reasonable assumption for a REST API.
            self.opnsense_client.post(reload_endpoint)
            logging.info(f"Successfully reloaded {bgp_implementation} service.")
        except Exception as e:
            logging.error(f"Failed to reload {bgp_implementation} service: {e}")

    def _get_node_ip(self, node):
        """
        Extracts the IP address from a Kubernetes Node object.
        Prefers InternalIP, then ExternalIP.
        """
        for addr in node.status.addresses:
            if addr.type == 'InternalIP':
                return addr.address
        for addr in node.status.addresses:
            if addr.type == 'ExternalIP':
                return addr.address
        return None
