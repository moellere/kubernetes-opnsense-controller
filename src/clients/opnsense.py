import requests
import os

class OpnSenseClient:
    def __init__(self, base_url, api_key, api_secret, verify=False):
        """
        Initializes the OPNsense API client.

        Args:
            base_url (str): The base URL of the OPNsense API.
            api_key (str): The API key for authentication.
            api_secret (str): The API secret for authentication.
            verify (bool): Whether to verify the SSL certificate. Defaults to False.
        """
        self.base_url = base_url
        self.auth = (api_key, api_secret)
        self.session = requests.Session()
        self.session.verify = verify

    def get(self, endpoint, params=None):
        """
        Sends a GET request to the OPNsense API.

        Args:
            endpoint (str): The API endpoint to call.
            params (dict, optional): The query parameters to include in the request. Defaults to None.

        Returns:
            dict: The JSON response from the API.
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, auth=self.auth, params=params)
        response.raise_for_status()
        return response.json()

    def post(self, endpoint, data=None):
        """
        Sends a POST request to the OPNsense API.

        Args:
            endpoint (str): The API endpoint to call.
            data (dict, optional): The JSON data to include in the request body. Defaults to None.

        Returns:
            dict: The JSON response from the API.
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, auth=self.auth, json=data)
        response.raise_for_status()
        return response.json()

    def put(self, endpoint, data=None):
        """
        Sends a PUT request to the OPNsense API.

        Args:
            endpoint (str): The API endpoint to call.
            data (dict, optional): The JSON data to include in the request body. Defaults to None.

        Returns:
            dict: The JSON response from the API.
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.put(url, auth=self.auth, json=data)
        response.raise_for_status()
        return response.json()

    def delete(self, endpoint):
        """
        Sends a DELETE request to the OPNsense API.

        Args:
            endpoint (str): The API endpoint to call.

        Returns:
            dict: The JSON response from the API.
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.delete(url, auth=self.auth)
        response.raise_for_status()
        return response.json()

def from_env():
    """
    Creates an OpnSenseClient instance from environment variables.
    """
    base_url = os.getenv("OPNSENSE_URL")
    api_key = os.getenv("OPNSENSE_API_KEY")
    api_secret = os.getenv("OPNSENSE_API_SECRET")

    if not all([base_url, api_key, api_secret]):
        raise ValueError("OPNSENSE_URL, OPNSENSE_API_KEY, and OPNSENSE_API_SECRET must be set")

    return OpnSenseClient(base_url, api_key, api_secret)
