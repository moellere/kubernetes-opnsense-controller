import logging

class DNSServicesPlugin:
    def __init__(self, k8s_core_v1_api, opnsense_client, config):
        self.k8s_core_v1_api = k8s_core_v1_api
        self.opnsense_client = opnsense_client
        self.config = config
        self.plugin_id = 'dns-services'
        self.annotation = 'dns.opnsense.org/hostname'

    def run(self):
        """
        Runs the reconciliation loop for the DNS Services plugin.
        """
        logging.info(f"Running {self.plugin_id} plugin reconciliation...")

        # 1. Get all Service resources
        try:
            services = self.k8s_core_v1_api.list_service_for_all_namespaces().items
        except Exception as e:
            logging.error(f"Error getting Service resources: {e}")
            return

        # 2. Process services to get desired state (DNS host overrides)
        desired_overrides = self._get_desired_state(services)

        # 3. Get current state from OPNsense
        # Assuming Unbound DNS is the target for now. A real implementation would
        # also handle dnsmasq based on config.
        current_overrides = self._get_opnsense_host_overrides()
        if current_overrides is None:
            return

        # 4. Reconcile
        self._reconcile_overrides(desired_overrides, current_overrides)

    def _get_desired_state(self, services):
        """
        Processes Service resources to build the desired list of DNS host overrides.
        """
        desired = {}
        for service in services:
            # Filter by type and annotation
            if service.spec.type != 'LoadBalancer':
                continue

            if self.annotation not in service.metadata.annotations:
                continue

            # Get hostname and IP
            hostname = service.metadata.annotations[self.annotation]
            ip = self._get_service_ip(service)

            if not ip:
                logging.warning(f"Service {service.metadata.namespace}/{service.metadata.name} has no external IP.")
                continue

            # Key for the map will be f"{hostname}.{domain}" but we need to figure out the domain.
            # The OPNsense API for host overrides uses a combination of host and domain.
            # Let's assume for now the hostname in the annotation is the FQDN.
            # We'll use the hostname as the key.

            # The API requires host, domain, and ip.
            # We'll split the hostname into host and domain parts.
            parts = hostname.split('.')
            if len(parts) < 2:
                logging.warning(f"Hostname '{hostname}' for service {service.metadata.name} is not a valid FQDN, skipping.")
                continue

            host = parts[0]
            domain = ".".join(parts[1:])

            desired[hostname] = {
                "host": host,
                "domain": domain,
                "ip": ip,
                "description": f"Managed by K8s Service {service.metadata.namespace}/{service.metadata.name}"
            }
        return desired

    def _get_service_ip(self, service):
        """
        Gets the external IP from a LoadBalancer service.
        """
        ingress = service.status.load_balancer.ingress
        if ingress and len(ingress) > 0:
            # Return the IP of the first ingress point
            return ingress[0].ip
        return None

    def _get_opnsense_host_overrides(self):
        """
        Gets the current host overrides from OPNsense Unbound DNS.
        """
        # Endpoint is a guess
        endpoint = '/api/unbound/settings/searchHostOverride'
        try:
            response = self.opnsense_client.get(endpoint)
            existing = {}
            if 'rows' in response:
                for row in response['rows']:
                    # Create a unique key for comparison
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
        logging.info("Reconciling Unbound DNS host overrides...")

        # Add/Update
        for key, data in desired.items():
            if key in current:
                # Check if update is needed
                if current[key].get('ip') != data['ip']:
                    logging.info(f"Updating host override for '{key}'")
                    uuid = current[key]['uuid']
                    # Endpoint is a guess
                    self.opnsense_client.post(f'/api/unbound/settings/setHostOverride/{uuid}', {'host': data})
            else:
                logging.info(f"Adding new host override for '{key}'")
                # Endpoint is a guess
                self.opnsense_client.post('/api/unbound/settings/addHostOverride', {'host': data})

        # Delete
        orphaned = {k: v for k, v in current.items() if k not in desired and v.get('description', '').startswith('Managed by K8s')}
        for key, item in orphaned.items():
            logging.info(f"Deleting orphaned host override: {key}")
            uuid = item['uuid']
            # Endpoint is a guess
            self.opnsense_client.post(f'/api/unbound/settings/delHostOverride/{uuid}')
