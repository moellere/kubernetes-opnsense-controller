import logging
from kubernetes import client

class HAProxyIngressProxyPlugin:
    def __init__(self, k8s_networking_v1_api, opnsense_client, config):
        self.k8s_networking_v1_api = k8s_networking_v1_api
        self.opnsense_client = opnsense_client
        self.config = config
        self.plugin_id = 'haproxy-ingress-proxy'

    def run(self):
        """
        Runs the reconciliation loop for the HAProxy Ingress Proxy plugin.
        """
        logging.info(f"Running {self.plugin_id} plugin reconciliation...")

        # 1. Get all Ingress resources
        try:
            ingresses = self.k8s_networking_v1_api.list_ingress_for_all_namespaces().items
        except client.ApiException as e:
            logging.error(f"Error getting Ingress resources: {e}")
            return

        # 2. Process ingresses to get desired state (ACLs and Actions)
        desired_acls, desired_actions = self._get_desired_state(ingresses)

        # 3. Get current state from OPNsense
        current_acls = self._get_opnsense_items('acl')
        current_actions = self._get_opnsense_items('action')
        if current_acls is None or current_actions is None:
            return

        # 4. Reconcile ACLs
        self._reconcile_items('acl', desired_acls, current_acls)

        # 5. Reconcile Actions
        # We need to refresh the ACL list from OPNsense so we can link actions to the new ACL UUIDs
        refreshed_acls = self._get_opnsense_items('acl')
        if refreshed_acls:
            self._reconcile_actions(desired_actions, current_actions, refreshed_acls)

    def _get_desired_state(self, ingresses):
        """
        Processes Ingress resources to build the desired list of HAProxy ACLs and Actions.
        """
        desired_acls = {}
        desired_actions = {}

        default_frontend = self.config.get('defaultFrontend')
        default_backend = self.config.get('defaultBackend')

        for ingress in ingresses:
            ingress_name = ingress.metadata.name
            ingress_ns = ingress.metadata.namespace

            # TODO: Handle annotations for enabling/disabling, and custom frontend/backend

            if not ingress.spec.rules:
                continue

            for rule in ingress.spec.rules:
                if not rule.host:
                    continue

                host = rule.host
                # Create a unique name for the ACL and Action based on the host
                acl_name = f"kic-{host}"
                action_name = f"kic-{host}"

                # Define the ACL
                desired_acls[acl_name] = {
                    "name": acl_name,
                    "expression": "host_matches", # This is a guess, needs verification
                    "value": host,
                    "description": f"Managed by K8s Ingress {ingress_ns}/{ingress_name}"
                }

                # Define the Action
                desired_actions[action_name] = {
                    "name": action_name,
                    "test_type": "if",
                    "acls": [acl_name], # Link to the ACL by name
                    "operator": "and",
                    "backend": default_backend # Use the default backend for now
                }

        return desired_acls, desired_actions

    def _reconcile_items(self, item_type, desired_map, current_map):
        """Generic reconciliation function for simple items like ACLs."""
        logging.info(f"Reconciling HAProxy {item_type}s...")

        # Add/Update
        for name, data in desired_map.items():
            if name in current_map:
                uuid = current_map[name]['uuid']
                # TODO: Check if update is needed
                logging.info(f"Updating {item_type} '{name}' (UUID: {uuid})")
                self._update_opnsense_item(item_type, uuid, data)
            else:
                logging.info(f"Adding new {item_type} '{name}'")
                self._add_opnsense_item(item_type, data)

        # Delete
        orphaned = {k: v for k, v in current_map.items() if k not in desired_map and k.startswith('kic-')}
        for name, item in orphaned.items():
            logging.info(f"Deleting orphaned {item_type}: {name}")
            self._delete_opnsense_item(item_type, item['uuid'])

    def _reconcile_actions(self, desired_actions, current_actions, current_acls):
        """Specific reconciliation for actions to link ACL UUIDs."""
        logging.info("Reconciling HAProxy Actions...")

        # Add/Update
        for name, data in desired_actions.items():
            # Replace ACL names with UUIDs
            acl_uuids = [current_acls[acl_name]['uuid'] for acl_name in data['acls'] if acl_name in current_acls]
            if not acl_uuids:
                logging.warning(f"Could not find UUIDs for ACLs of action '{name}', skipping.")
                continue

            data['acls'] = ",".join(acl_uuids) # API likely takes comma-separated UUIDs

            if name in current_actions:
                uuid = current_actions[name]['uuid']
                logging.info(f"Updating action '{name}' (UUID: {uuid})")
                self._update_opnsense_item('action', uuid, data)
            else:
                logging.info(f"Adding new action '{name}'")
                self._add_opnsense_item('action', data)

        # Delete (same as generic)
        orphaned = {k: v for k, v in current_actions.items() if k not in desired_actions and k.startswith('kic-')}
        for name, item in orphaned.items():
            logging.info(f"Deleting orphaned action: {name}")
            self._delete_opnsense_item('action', item['uuid'])


    # --- Generic OPNsense API Functions (can be moved to a shared module) ---
    def _get_opnsense_items(self, item_type):
        """Generic function to get items from OPNsense."""
        # These endpoints are guesses
        endpoint = f'/api/haproxy/{item_type}/search'
        try:
            response = self.opnsense_client.get(endpoint)
            return {row['name']: row for row in response.get('rows', []) if 'name' in row}
        except Exception as e:
            # A 404 might just mean the endpoint guess was wrong.
            logging.error(f"Error getting HAProxy {item_type}s: {e}")
            return None

    def _add_opnsense_item(self, item_type, item_data):
        endpoint = f'/api/haproxy/{item_type}/add'
        try:
            # The payload structure is a guess: { "acl": { ... } }
            self.opnsense_client.post(endpoint, {item_type: item_data})
        except Exception as e:
            logging.error(f"Failed to add {item_type} {item_data.get('name')}: {e}")

    def _update_opnsense_item(self, item_type, uuid, item_data):
        endpoint = f'/api/haproxy/{item_type}/set/{uuid}'
        try:
            self.opnsense_client.post(endpoint, {item_type: item_data})
        except Exception as e:
            logging.error(f"Failed to update {item_type} {item_data.get('name')}: {e}")

    def _delete_opnsense_item(self, item_type, uuid):
        endpoint = f'/api/haproxy/{item_type}/del/{uuid}'
        try:
            self.opnsense_client.post(endpoint)
        except Exception as e:
            logging.error(f"Failed to delete {item_type} with UUID {uuid}: {e}")
