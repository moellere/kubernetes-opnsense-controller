import logging

class DNSHAProxyIngressProxyPlugin:
    def __init__(self, k8s_networking_v1_api, opnsense_client, config, haproxy_ingress_proxy_config):
        self.k8s_networking_v1_api = k8s_networking_v1_api
        self.opnsense_client = opnsense_client
        self.config = config
        self.haproxy_ingress_proxy_config = haproxy_ingress_proxy_config # Need this for default frontend
        self.plugin_id = 'dns-haproxy-ingress-proxy'
        self.annotation_frontend = 'haproxy-ingress-proxy.opnsense.org/frontend'

    def run(self):
        """
        Runs the reconciliation loop for the DNS HAProxy Ingress Proxy plugin.
        """
        logging.info(f"Running {self.plugin_id} plugin reconciliation...")

        try:
            ingresses = self.k8s_networking_v1_api.list_ingress_for_all_namespaces().items
        except Exception as e:
            logging.error(f"Error getting Ingress resources: {e}")
            return

        desired_aliases = self._get_desired_state(ingresses)
        current_aliases = self._get_opnsense_host_aliases()
        if current_aliases is None:
            return

        self._reconcile_aliases(desired_aliases, current_aliases)

    def _get_desired_state(self, ingresses):
        """
        Processes Ingress resources to build the desired list of DNS host aliases.
        """
        desired = {}
        configured_frontends = self.config.get('frontends', {})

        for ingress in ingresses:
            # Determine the target frontend for this ingress
            annotations = ingress.metadata.annotations or {}
            target_frontend = annotations.get(self.annotation_frontend, self.haproxy_ingress_proxy_config.get('defaultFrontend'))

            if not target_frontend or target_frontend not in configured_frontends:
                continue

            base_hostname = configured_frontends[target_frontend].get('hostname')
            if not base_hostname:
                continue

            if not ingress.spec.rules:
                continue

            for rule in ingress.spec.rules:
                if not rule.host:
                    continue

                alias_host = rule.host
                # OPNsense API for aliases uses host and domain for the alias, and then a reference to the target host object.
                # It's simpler if we assume the API just takes the alias name and the target hostname string.
                # We'll model our desired state that way. Key by the alias hostname.

                desired[alias_host] = {
                    "host": alias_host,
                    "target": base_hostname,
                    "description": f"Managed by K8s Ingress {ingress.metadata.namespace}/{ingress.metadata.name}"
                }
        return desired

    def _get_opnsense_host_aliases(self):
        """
        Gets the current host aliases from OPNsense Unbound DNS.
        """
        # Endpoint is a guess
        endpoint = '/api/unbound/settings/searchHostAlias'
        try:
            response = self.opnsense_client.get(endpoint)
            existing = {}
            if 'rows' in response:
                for row in response['rows']:
                    # Use hostname as the key
                    if 'hostname' in row:
                        existing[row['hostname']] = row
            return existing
        except Exception as e:
            logging.error(f"Error getting OPNsense Unbound host aliases: {e}")
            return None

    def _reconcile_aliases(self, desired, current):
        """
        Reconciles DNS host aliases.
        """
        logging.info("Reconciling Unbound DNS host aliases...")

        # Add/Update
        for key, data in desired.items():
            payload = { "alias": data } # API payload structure is a guess
            if key in current:
                if current[key].get('target') != data['target']:
                    logging.info(f"Updating host alias for '{key}'")
                    uuid = current[key]['uuid']
                    self.opnsense_client.post(f'/api/unbound/settings/setHostAlias/{uuid}', payload)
            else:
                logging.info(f"Adding new host alias for '{key}'")
                self.opnsense_client.post('/api/unbound/settings/addHostAlias', payload)

        # Delete
        orphaned = {k: v for k, v in current.items() if k not in desired and v.get('description', '').startswith('Managed by K8s')}
        for key, item in orphaned.items():
            logging.info(f"Deleting orphaned host alias: {key}")
            uuid = item['uuid']
            self.opnsense_client.post(f'/api/unbound/settings/delHostAlias/{uuid}')
