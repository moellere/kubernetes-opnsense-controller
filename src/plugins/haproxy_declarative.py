import logging
import yaml
from kubernetes import client

class HAProxyDeclarativePlugin:
    def __init__(self, k8s_core_v1_api, opnsense_client, config):
        self.k8s_core_v1_api = k8s_core_v1_api
        self.opnsense_client = opnsense_client
        self.config = config
        self.plugin_id = 'haproxy-declarative'

    def run(self):
        logging.info(f"Running {self.plugin_id} plugin reconciliation...")

        declarative_cms = self._get_declarative_configmaps()
        if declarative_cms is None:
            return

        all_desired_resources = []
        for cm in declarative_cms:
            resources = self._parse_cm_resources(cm)
            if resources:
                all_desired_resources.extend(resources)

        self._reconcile_resources(all_desired_resources)

    def _get_declarative_configmaps(self):
        logging.info("Getting declarative HAProxy ConfigMaps...")
        try:
            label_selector = 'pfsense.org/type=declarative'
            return self.k8s_core_v1_api.list_config_map_for_all_namespaces(label_selector=label_selector).items
        except client.ApiException as e:
            logging.error(f"Error getting declarative ConfigMaps: {e}")
            return None

    def _parse_cm_resources(self, cm):
        cm_name = cm.metadata.name
        cm_namespace = cm.metadata.namespace
        logging.info(f"Parsing ConfigMap: {cm_namespace}/{cm_name}")
        try:
            config_data_str = cm.data.get('data')
            if not config_data_str:
                return None
            config_data = yaml.safe_load(config_data_str)
            if not config_data or 'resources' not in config_data:
                return None

            resources = config_data['resources']
            for res in resources:
                res['metadata'] = {'namespace': cm_namespace, 'cm_name': cm_name}
            return resources
        except yaml.YAMLError as e:
            logging.error(f"Error parsing YAML from ConfigMap {cm_namespace}/{cm_name}: {e}")
            return None

    def _reconcile_resources(self, desired_resources):
        desired_backends = [r for r in desired_resources if r.get('type') == 'backend']
        desired_frontends = [r for r in desired_resources if r.get('type') == 'frontend']

        # Reconcile backends first, as frontends may depend on them
        self._reconcile_backends(desired_backends)
        self._reconcile_frontends(desired_frontends)

    def _reconcile_backends(self, desired_backends):
        current_backends = self._get_opnsense_items('backend')
        if current_backends is None: return

        desired_map = {b.get('definition', {}).get('name'): b for b in desired_backends if b.get('definition', {}).get('name')}

        for name, backend_data in desired_map.items():
            resolved_backend = self._resolve_backend_servers(backend_data)
            if name in current_backends:
                uuid = current_backends[name]['uuid']
                logging.info(f"Updating backend '{name}' (UUID: {uuid})")
                self._update_opnsense_item('backend', uuid, resolved_backend['definition'])
            else:
                logging.info(f"Adding new backend '{name}'")
                self._add_opnsense_item('backend', resolved_backend['definition'])

        orphaned = {k: v for k, v in current_backends.items() if k not in desired_map}
        for name, backend in orphaned.items():
            # TODO: Add a check to only delete managed backends, e.g., by a special description/label
            logging.info(f"Deleting orphaned backend: {name}")
            self._delete_opnsense_item('backend', backend['uuid'])

    def _reconcile_frontends(self, desired_frontends):
        current_frontends = self._get_opnsense_items('frontend')
        if current_frontends is None: return

        desired_map = {f.get('definition', {}).get('name'): f for f in desired_frontends if f.get('definition', {}).get('name')}

        for name, frontend_data in desired_map.items():
            if name in current_frontends:
                uuid = current_frontends[name]['uuid']
                logging.info(f"Updating frontend '{name}' (UUID: {uuid})")
                self._update_opnsense_item('frontend', uuid, frontend_data['definition'])
            else:
                logging.info(f"Adding new frontend '{name}'")
                self._add_opnsense_item('frontend', frontend_data['definition'])

        orphaned = {k: v for k, v in current_frontends.items() if k not in desired_map}
        for name, frontend in orphaned.items():
            logging.info(f"Deleting orphaned frontend: {name}")
            self._delete_opnsense_item('frontend', frontend['uuid'])

    def _resolve_backend_servers(self, backend_data):
        if 'ha_servers' not in backend_data:
            return backend_data

        resolved_servers = []
        for server in backend_data['ha_servers']:
            server_def = server.get('definition', {})

            if server.get('type') == 'node-static':
                resolved_servers.append(server_def)

            elif server.get('type') == 'node-service':
                service_name = server.get('serviceName')
                service_port = server.get('servicePort')
                namespace = server.get('serviceNamespace') or backend_data.get('metadata', {}).get('namespace')

                if not all([service_name, service_port, namespace]):
                    logging.warning(f"Skipping node-service in backend '{backend_data.get('definition', {}).get('name')}' due to missing info.")
                    continue

                try:
                    service = self.k8s_core_v1_api.read_namespaced_service(name=service_name, namespace=namespace)
                    node_port = next((p.node_port for p in service.spec.ports if p.port == service_port), None)

                    if not node_port:
                        logging.warning(f"Service {namespace}/{service_name} has no matching nodePort for port {service_port}")
                        continue

                    nodes = self.k8s_core_v1_api.list_node().items
                    for node in nodes:
                        node_ip = self._get_node_ip(node)
                        if node_ip:
                            new_server = server_def.copy()
                            new_server['name'] = f"{node.metadata.name}-{service_port}"
                            new_server['address'] = node_ip
                            new_server['port'] = node_port
                            resolved_servers.append(new_server)
                except client.ApiException as e:
                    logging.error(f"Error getting service {namespace}/{service_name}: {e}")

        backend_data['definition']['servers'] = resolved_servers
        del backend_data['ha_servers']
        return backend_data

    def _get_node_ip(self, node):
        addrs = node.status.addresses
        return next((a.address for a in addrs if a.type == 'InternalIP'),
                    next((a.address for a in addrs if a.type == 'ExternalIP'), None))

    # --- Generic OPNsense API Functions ---
    def _get_opnsense_items(self, item_type):
        endpoint = f'/api/haproxy/settings/search_{item_type}'
        try:
            response = self.opnsense_client.get(endpoint)
            return {row['name']: row for row in response.get('rows', []) if 'name' in row}
        except Exception as e:
            logging.error(f"Error getting HAProxy {item_type}s: {e}")
            return None

    def _add_opnsense_item(self, item_type, item_data):
        endpoint = f'/api/haproxy/settings/add_{item_type}'
        try:
            self.opnsense_client.post(endpoint, {item_type: item_data})
        except Exception as e:
            logging.error(f"Failed to add {item_type} {item_data.get('name')}: {e}")

    def _update_opnsense_item(self, item_type, uuid, item_data):
        endpoint = f'/api/haproxy/settings/set_{item_type}/{uuid}'
        try:
            self.opnsense_client.post(endpoint, {item_type: item_data})
        except Exception as e:
            logging.error(f"Failed to update {item_type} {item_data.get('name')}: {e}")

    def _delete_opnsense_item(self, item_type, uuid):
        endpoint = f'/api/haproxy/settings/del_{item_type}/{uuid}'
        try:
            self.opnsense_client.post(endpoint)
        except Exception as e:
            logging.error(f"Failed to delete {item_type} with UUID {uuid}: {e}")
