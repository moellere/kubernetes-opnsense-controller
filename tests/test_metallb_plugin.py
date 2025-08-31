import unittest
from unittest.mock import MagicMock, patch, call
from src.plugins.metallb import MetalLBPlugin

# Mock Kubernetes objects
class MockV1Node:
    def __init__(self, name, internal_ip):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.status = MagicMock()
        self.status.addresses = [
            MagicMock(type='InternalIP', address=internal_ip)
        ]

class MockV1NodeList:
    def __init__(self, items):
        self.items = items

class TestMetalLBPlugin(unittest.TestCase):

    def setUp(self):
        self.k8s_core_v1_api = MagicMock()
        self.opnsense_client = MagicMock()
        self.config = {
            'bgp-implementation': 'frr',
            'options': {
                'frr': {
                    'template': {
                        'peergroup': 'metallb',
                        'some_other_setting': 'value'
                    }
                }
            }
        }
        self.plugin = MetalLBPlugin(self.k8s_core_v1_api, self.opnsense_client, self.config)

    def test_reconciliation_logic(self):
        # --- Arrange ---
        # 1. Mock Kubernetes Nodes
        nodes = [
            MockV1Node('node-1', '10.0.0.1'), # Should be updated
            MockV1Node('node-2', '10.0.0.2'), # Should be added
        ]
        self.k8s_core_v1_api.list_node.return_value = MockV1NodeList(nodes)

        # 2. Mock OPNsense Neighbors
        existing_neighbors = {
            'rows': [
                {
                    'uuid': 'uuid-1',
                    'description': 'kpc-10.0.0.1', # Existing, but needs update
                    'address': '10.0.0.1',
                    'peergroup': 'old-group'
                },
                {
                    'uuid': 'uuid-3',
                    'description': 'kpc-10.0.0.3', # Orphaned, should be deleted
                    'address': '10.0.0.3',
                    'peergroup': 'metallb'
                }
            ]
        }
        self.opnsense_client.get.return_value = existing_neighbors

        # --- Act ---
        self.plugin.run()

        # --- Assert ---
        # 1. Verify what was fetched
        self.k8s_core_v1_api.list_node.assert_called_once()
        self.opnsense_client.get.assert_called_once_with('/api/frr/settings/search_bgp_neighbor')

        # 2. Verify what was changed in OPNsense
        self.assertEqual(self.opnsense_client.post.call_count, 4)

        # Define expected calls
        expected_update_payload = {
            'neighbor': {
                'address': '10.0.0.1',
                'description': 'kpc-10.0.0.1',
                'peergroup': 'metallb',
                'some_other_setting': 'value'
            }
        }
        expected_add_payload = {
            'neighbor': {
                'address': '10.0.0.2',
                'description': 'kpc-10.0.0.2',
                'peergroup': 'metallb',
                'some_other_setting': 'value'
            }
        }

        # Check the calls using assert_any_call
        self.opnsense_client.post.assert_any_call('/api/frr/settings/set_bgp_neighbor/uuid-1', expected_update_payload)
        self.opnsense_client.post.assert_any_call('/api/frr/settings/add_bgp_neighbor', expected_add_payload)
        self.opnsense_client.post.assert_any_call('/api/frr/settings/del_bgp_neighbor/uuid-3')

        # 3. Verify that the BGP service was reloaded
        self.opnsense_client.post.assert_any_call('/api/frr/service/reload')

if __name__ == '__main__':
    unittest.main()
