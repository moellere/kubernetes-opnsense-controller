<?php

namespace KubernetesOpnSenseController;

use GuzzleHttp\Client as GuzzleClient;

class Client
{
    private $client;
    private $apiKey;
    private $apiSecret;
    private $baseUrl;

    public function __construct($baseUrl, $apiKey, $apiSecret)
    {
        $this->baseUrl = $baseUrl;
        $this->apiKey = $apiKey;
        $this->apiSecret = $apiSecret;

        $this->client = new GuzzleClient([
            'base_uri' => $this->baseUrl,
            'auth' => [$this->apiKey, $this->apiSecret],
            'timeout'  => 10.0,
            'verify' => false, // In a production environment, you should use a proper certificate
        ]);
    }

    public function get($endpoint, $params = [])
    {
        $response = $this->client->get($endpoint, ['query' => $params]);
        return json_decode($response->getBody(), true);
    }

    public function post($endpoint, $data = [])
    {
        $response = $this->client->post($endpoint, ['json' => $data]);
        return json_decode($response->getBody(), true);
    }

    public function put($endpoint, $data = [])
    {
        $response = $this->client->put($endpoint, ['json' => $data]);
        return json_decode($response->getBody(), true);
    }

    public function delete($endpoint)
    {
        $response = $this->client->delete($endpoint);
        return json_decode($response->getBody(), true);
    }
}
