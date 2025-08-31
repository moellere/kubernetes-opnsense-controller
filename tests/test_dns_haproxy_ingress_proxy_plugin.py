import unittest
from unittest.mock import MagicMock
from src.plugins.dns_haproxy_ingress_proxy import DNSHAProxyIngressProxyPlugin

# Mock Kubernetes objects
class MockV1Ingress:
    def __init__(self, name, namespace, rules, annotations=None):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.metadata.namespace = namespace
        self.metadata.annotations = annotations or {}
        self.spec = MagicMock()
        self.spec.rules = [MagicMock(host=host) for host in rules]

class MockV1IngressList:
    def __init__(self, items):
        self.items = items

class TestDNSHAProxyIngressProxyPlugin(unittest.TestCase):

    def setUp(self):
        self.k8s_networking_v1_api = MagicMock()
        self.opnsense_client = MagicMock()
        self.config = {
            'frontends': {
                'http-80': { 'hostname': 'http-80.k8s' },
                'http-443': { 'hostname': 'https-443.k8s' }
            }
        }
        self.haproxy_ingress_proxy_config = {
            'defaultFrontend': 'http-80'
        }
        self.plugin = DNSHAProxyIngressProxyPlugin(
            self.k8s_networking_v1_api,
            self.opnsense_client,
            self.config,
            self.haproxy_ingress_proxy_config
        )

    def test_dns_haproxy_reconciliation(self):
        # --- Arrange ---
        ingresses = [
            MockV1Ingress('ingress-add', 'default', ['add.example.com']),
            MockV1Ingress('ingress-update', 'default', ['update.example.com'], {'haproxy-ingress-proxy.opnsense.org/frontend': 'http-443'}),
            MockV1Ingress('ingress-ignore', 'default', ['ignore.example.com'], {'haproxy-ingress-proxy.opnsense.org/frontend': 'tcp-9000'}),
        ]
        self.k8s_networking_v1_api.list_ingress_for_all_namespaces.return_value = MockV1IngressList(ingresses)

        existing_aliases = {
            'rows': [
                {'uuid': 'uuid-update', 'hostname': 'update.example.com', 'target': 'old.target.k8s', 'description': 'Managed by K8s'},
                {'uuid': 'uuid-delete', 'hostname': 'delete.example.com', 'target': 'http-80.k8s', 'description': 'Managed by K8s Ingress'}
            ]
        }
        self.opnsense_client.get.return_value = existing_aliases

        # --- Act ---
        self.plugin.run()

        # --- Assert ---
        self.opnsense_client.get.assert_called_once_with('/api/unbound/settings/searchHostAlias')

        calls = self.opnsense_client.post.call_args_list
        self.assertEqual(len(calls), 3)

        # Correctly access positional arguments from the mock call
        add_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/addHostAlias')
        self.assertEqual(add_call.args[1]['alias']['host'], 'add.example.com')
        self.assertEqual(add_call.args[1]['alias']['target'], 'http-80.k8s')

        update_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/setHostAlias/uuid-update')
        self.assertEqual(update_call.args[1]['alias']['host'], 'update.example.com')
        self.assertEqual(update_call.args[1]['alias']['target'], 'https-443.k8s')

        delete_call = next(c for c in calls if c.args[0] == '/api/unbound/settings/delHostAlias/uuid-delete')
        self.assertIsNotNone(delete_call)

if __name__ == '__main__':
    unittest.main()
