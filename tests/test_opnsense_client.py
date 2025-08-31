import unittest
import requests
from unittest.mock import patch, MagicMock
from src.clients.opnsense import OpnSenseClient

class TestOpnSenseClient(unittest.TestCase):

    def setUp(self):
        self.base_url = "https://opnsense.test/api"
        self.api_key = "test_key"
        self.api_secret = "test_secret"
        self.client = OpnSenseClient(self.base_url, self.api_key, self.api_secret, verify=False)

    @patch('requests.Session.get')
    def test_get_success(self, mock_get):
        # Mock the response from requests.get
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        # Call the method to test
        endpoint = "/health"
        response = self.client.get(endpoint)

        # Assertions
        mock_get.assert_called_once_with(
            f"{self.base_url}{endpoint}",
            auth=(self.api_key, self.api_secret),
            params=None
        )
        self.assertEqual(response, {"status": "ok"})

    @patch('requests.Session.post')
    def test_post_success(self, mock_post):
        # Mock the response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "saved"}
        mock_post.return_value = mock_response

        # Call the method
        endpoint = "/endpoint/add"
        data = {"key": "value"}
        response = self.client.post(endpoint, data=data)

        # Assertions
        mock_post.assert_called_once_with(
            f"{self.base_url}{endpoint}",
            auth=(self.api_key, self.api_secret),
            json=data
        )
        self.assertEqual(response, {"result": "saved"})

    @patch('requests.Session.get')
    def test_request_failure(self, mock_get):
        # Mock a failed response
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Not Found")
        mock_get.return_value = mock_response

        # Assert that an exception is raised
        with self.assertRaises(requests.exceptions.HTTPError):
            self.client.get("/nonexistent")

if __name__ == '__main__':
    unittest.main()
