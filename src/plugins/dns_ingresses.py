import logging

class DNSIngressesPlugin:
    def __init__(self, k8s_networking_v1_api, opnsense_client, config):
        self.k8s_networking_v1_api = k8s_networking_v1_api
        self.opnsense_client = opnsense_client
        self.config = config
        self.plugin_id = 'dns-ingresses'

    def run(self):
        """
        Runs the reconciliation loop for the DNS Ingresses plugin.
        """
        logging.info(f"Running {self.plugin_id} plugin reconciliation...")

        # 1. Get all Ingress resources
        try:
            ingresses = self.k8s_networking_v1_api.list_ingress_for_all_namespaces().items
        except Exception as e:
            logging.error(f"Error getting Ingress resources: {e}")
            return

        # 2. Process ingresses to get desired state
        desired_overrides = self._get_desired_state(ingresses)

        # 3. Get current state from OPNsense
        current_overrides = self._get_opnsense_host_overrides()
        if current_overrides is None:
            return

        # 4. Reconcile
        self._reconcile_overrides(desired_overrides, current_overrides)

    def _get_desired_state(self, ingresses):
        """
        Processes Ingress resources to build the desired list of DNS host overrides.
        """
        desired = {}
        for ingress in ingresses:
            # TODO: Handle annotations for enabling/disabling

            ip = self._get_ingress_ip(ingress)
            if not ip:
                logging.warning(f"Ingress {ingress.metadata.namespace}/{ingress.metadata.name} has no external IP.")
                continue

            if not ingress.spec.rules:
                continue

            for rule in ingress.spec.rules:
                if not rule.host:
                    continue

                hostname = rule.host
                parts = hostname.split('.')
                if len(parts) < 2:
                    logging.warning(f"Hostname '{hostname}' for ingress {ingress.metadata.name} is not a valid FQDN, skipping.")
                    continue

                host = parts[0]
                domain = ".".join(parts[1:])

                desired[hostname] = {
                    "host": host,
                    "domain": domain,
                    "ip": ip,
                    "description": f"Managed by K8s Ingress {ingress.metadata.namespace}/{ingress.metadata.name}"
                }
        return desired

    def _get_ingress_ip(self, ingress):
        """
        Gets the external IP from an Ingress resource.
        """
        lb_ingress = ingress.status.load_balancer.ingress
        if lb_ingress and len(lb_ingress) > 0:
            return lb_ingress[0].ip
        return None

    def _get_opnsense_host_overrides(self):
        """
        Gets the current host overrides from OPNsense Unbound DNS.
        """
        endpoint = '/api/unbound/settings/searchHostOverride'
        try:
            response = self.opnsense_client.get(endpoint)
            existing = {}
            if 'rows' in response:
                for row in response['rows']:
                    key = f"{row.get('host')}.{row.get('domain')}"
                    existing[key] = row
            return existing
        except Exception as e:
            logging.error(f"Error getting OPNsense Unbound host overrides: {e}")
            return None

    def _reconcile_overrides(self, desired, current):
        """
        Reconciles DNS host overrides.
        """
        logging.info("Reconciling Unbound DNS host overrides for Ingresses...")

        # Add/Update
        for key, data in desired.items():
            if key in current:
                if current[key].get('ip') != data['ip']:
                    logging.info(f"Updating host override for '{key}'")
                    uuid = current[key]['uuid']
                    self.opnsense_client.post(f'/api/unbound/settings/setHostOverride/{uuid}', {'host': data})
            else:
                logging.info(f"Adding new host override for '{key}'")
                self.opnsense_client.post('/api/unbound/settings/addHostOverride', {'host': data})

        # Delete
        orphaned = {k: v for k, v in current.items() if k not in desired and v.get('description', '').startswith('Managed by K8s Ingress')}
        for key, item in orphaned.items():
            logging.info(f"Deleting orphaned host override: {key}")
            uuid = item['uuid']
            self.opnsense_client.post(f'/api/unbound/settings/delHostOverride/{uuid}')
