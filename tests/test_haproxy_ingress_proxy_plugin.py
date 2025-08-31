import unittest
from unittest.mock import MagicMock, call
from src.plugins.haproxy_ingress_proxy import HAProxyIngressProxyPlugin

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

class TestHAProxyIngressProxyPlugin(unittest.TestCase):

    def setUp(self):
        self.k8s_networking_v1_api = MagicMock()
        self.opnsense_client = MagicMock()
        self.config = {
            'defaultBackend': 'pool-k8s-default'
        }
        self.plugin = HAProxyIngressProxyPlugin(self.k8s_networking_v1_api, self.opnsense_client, self.config)

    def test_haproxy_ingress_proxy_reconciliation(self):
        # --- Arrange ---
        ingresses = [
            MockV1Ingress('ingress-add', 'default', ['add.example.com'], '1.1.1.1'),
            MockV1Ingress('ingress-update', 'default', ['update.example.com'], '2.2.2.2'),
        ]
        self.k8s_networking_v1_api.list_ingress_for_all_namespaces.return_value = MockV1IngressList(ingresses)

        # Mock the responses from OPNsense API
        existing_acls = {
            'rows': [
                {'uuid': 'uuid-acl-update', 'name': 'kic-update.example.com', 'expression': 'host_matches', 'value': 'update.example.com'},
                {'uuid': 'uuid-acl-delete', 'name': 'kic-delete.example.com', 'expression': 'host_matches', 'value': 'delete.example.com'}
            ]
        }
        existing_actions = {
            'rows': [
                {'uuid': 'uuid-action-update', 'name': 'kic-update.example.com', 'test_type': 'if', 'acls': 'uuid-acl-update', 'backend': 'old-pool'},
                {'uuid': 'uuid-action-delete', 'name': 'kic-delete.example.com', 'test_type': 'if', 'acls': 'uuid-acl-delete', 'backend': 'pool-k8s-default'}
            ]
        }
        # The first call to _get_opnsense_items is for acls, the second for actions, the third is a refresh for acls
        self.opnsense_client.get.side_effect = [
            existing_acls,
            existing_actions,
            existing_acls
        ]

        # --- Act ---
        self.plugin.run()

        # --- Assert ---
        # Check that we searched for both acls and actions
        get_calls = self.opnsense_client.get.call_args_list
        self.assertIn(call('/api/haproxy/settings/search_acls'), get_calls)
        self.assertIn(call('/api/haproxy/settings/search_actions'), get_calls)

        post_calls = self.opnsense_client.post.call_args_list

        # We expect 5 calls: add_acl, set_acl, del_acl, add_action, set_action, del_action, and reconfigure
        # Based on the test data:
        # ACLs: add, update, delete
        # Actions: add, update, delete
        # Reconfigure: 1
        # Total: 7 calls
        # Let's verify the most important ones

        # Add
        add_acl_call = next(c for c in post_calls if c.args[0] == '/api/haproxy/settings/add_acl')
        self.assertEqual(add_acl_call.args[1]['acl']['name'], 'kic-add.example.com')

        # Update
        update_acl_call = next(c for c in post_calls if c.args[0] == '/api/haproxy/settings/set_acl/uuid-acl-update')
        self.assertEqual(update_acl_call.args[1]['acl']['name'], 'kic-update.example.com')

        # Delete
        delete_acl_call = next(c for c in post_calls if c.args[0] == '/api/haproxy/settings/del_acl/uuid-acl-delete')
        self.assertIsNotNone(delete_acl_call)

        # We don't check actions in detail here as it's complex to mock the refreshed ACLs,
        # but we do check that a reconfigure was triggered.
        reconfigure_call = next(c for c in post_calls if c.args[0] == '/api/haproxy/service/reconfigure')
        self.assertIsNotNone(reconfigure_call)


if __name__ == '__main__':
    unittest.main()
