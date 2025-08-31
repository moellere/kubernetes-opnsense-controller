import unittest
from unittest.mock import MagicMock
from src.plugins.dns_ingresses import DNSIngressesPlugin

# Mock Kubernetes objects
class MockV1Ingress:
    def __init__(self, name, namespace, rules, ip):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.metadata.namespace = namespace
        self.spec = MagicMock()
        self.spec.rules = [MagicMock(host=host) for host in rules]
        self.status = MagicMock()
        self.status.load_balancer = MagicMock()
        if ip:
            self.status.load_balancer.ingress = [MagicMock(ip=ip)]
        else:
            self.status.load_balancer.ingress = []

class MockV1IngressList:
    def __init__(self, items):
        self.items = items

class TestDNSIngressesPlugin(unittest.TestCase):

    def setUp(self):
        self.k8s_networking_v1_api = MagicMock()
        self.opnsense_client = MagicMock()
        self.config = {}
        self.plugin = DNSIngressesPlugin(self.k8s_networking_v1_api, self.opnsense_client, self.config)

    def test_dns_ingresses_reconciliation(self):
        # --- Arrange ---
        ingresses = [
            MockV1Ingress('ingress-add', 'default', ['add.example.com'], '1.1.1.1'),
            MockV1Ingress('ingress-update', 'default', ['update.example.com'], '2.2.2.2'),
            MockV1Ingress('ingress-ignore', 'default', ['ignore.example.com'], None),
        ]
        self.k8s_networking_v1_api.list_ingress_for_all_namespaces.return_value = MockV1IngressList(ingresses)

        existing_overrides = {
            'rows': [
                {'uuid': 'uuid-update', 'host': 'update', 'domain': 'example.com', 'ip': '8.8.8.8', 'description': 'Managed by K8s Ingress'},
                {'uuid': 'uuid-delete', 'host': 'delete', 'domain': 'example.com', 'ip': '9.9.9.9', 'description': 'Managed by K8s Ingress some/other-ingress'}
            ]
        }
        self.opnsense_client.get.return_value = existing_overrides

        # --- Act ---
        self.plugin.run()

        # --- Assert ---
        self.opnsense_client.get.assert_called_once_with('/api/unbound/settings/search_host_override')

        calls = self.opnsense_client.post.call_args_list
        self.assertEqual(len(calls), 4)

        # Correctly access positional arguments from the mock call
        add_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/add_host_override')
        self.assertEqual(add_call.args[1]['host']['host'], 'add')
        self.assertEqual(add_call.args[1]['host']['ip'], '1.1.1.1')

        update_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/set_host_override/uuid-update')
        self.assertEqual(update_call.args[1]['host']['host'], 'update')
        self.assertEqual(update_call.args[1]['host']['ip'], '2.2.2.2')

        delete_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/del_host_override/uuid-delete')
        self.assertIsNotNone(delete_call)

        reconfigure_call = next(c for c in calls if c.args[0] == '/api/unbound/service/reconfigure')
        self.assertIsNotNone(reconfigure_call)

if __name__ == '__main__':
    unittest.main()
