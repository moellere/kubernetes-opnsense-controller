import unittest
from unittest.mock import MagicMock
from src.plugins.dns_services import DNSServicesPlugin

# Mock Kubernetes objects
class MockV1Service:
    def __init__(self, name, namespace, service_type, annotations, ip):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.metadata.namespace = namespace
        self.metadata.annotations = annotations
        self.spec = MagicMock()
        self.spec.type = service_type
        self.status = MagicMock()
        self.status.load_balancer = MagicMock()
        if ip:
            self.status.load_balancer.ingress = [MagicMock(ip=ip)]
        else:
            self.status.load_balancer.ingress = []

class MockV1ServiceList:
    def __init__(self, items):
        self.items = items

class TestDNSServicesPlugin(unittest.TestCase):

    def setUp(self):
        self.k8s_core_v1_api = MagicMock()
        self.opnsense_client = MagicMock()
        self.config = {}
        self.plugin = DNSServicesPlugin(self.k8s_core_v1_api, self.opnsense_client, self.config)
        self.plugin.annotation = 'dns.opnsense.org/hostname'

    def test_dns_services_reconciliation(self):
        # --- Arrange ---
        services = [
            MockV1Service('web-svc-add', 'default', 'LoadBalancer', {self.plugin.annotation: 'add.example.com'}, '1.1.1.1'),
            MockV1Service('web-svc-update', 'default', 'LoadBalancer', {self.plugin.annotation: 'update.example.com'}, '2.2.2.2'),
            MockV1Service('web-svc-ignore', 'default', 'ClusterIP', {self.plugin.annotation: 'ignore.example.com'}, '3.3.3.3'),
            MockV1Service('web-svc-ignore-2', 'default', 'LoadBalancer', {}, '4.4.4.4'),
        ]
        self.k8s_core_v1_api.list_service_for_all_namespaces.return_value = MockV1ServiceList(services)

        existing_overrides = {
            'rows': [
                {'uuid': 'uuid-update', 'host': 'update', 'domain': 'example.com', 'ip': '8.8.8.8', 'description': 'Managed by K8s'},
                {'uuid': 'uuid-delete', 'host': 'delete', 'domain': 'example.com', 'ip': '9.9.9.9', 'description': 'Managed by K8s Service some/other-service'}
            ]
        }
        self.opnsense_client.get.return_value = existing_overrides

        # --- Act ---
        self.plugin.run()

        # --- Assert ---
        self.opnsense_client.get.assert_called_once_with('/api/unbound/settings/searchHostOverride')

        calls = self.opnsense_client.post.call_args_list
        self.assertEqual(len(calls), 3)

        # Correctly access positional arguments from the mock call
        add_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/addHostOverride')
        self.assertEqual(add_call.args[1]['host']['host'], 'add')
        self.assertEqual(add_call.args[1]['host']['ip'], '1.1.1.1')

        update_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/setHostOverride/uuid-update')
        self.assertEqual(update_call.args[1]['host']['host'], 'update')
        self.assertEqual(update_call.args[1]['host']['ip'], '2.2.2.2')

        delete_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/delHostOverride/uuid-delete')
        self.assertIsNotNone(delete_call)

if __name__ == '__main__':
    unittest.main()
