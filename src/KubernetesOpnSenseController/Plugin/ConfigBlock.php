<?php

namespace KubernetesOpnSenseController\Plugin;

class ConfigBlock
{
    public $data;
    private $client;
    private $sectionName;

    public function __construct($client, $data, $sectionName)
    {
        $this->client = $client;
        $this->data = $data;
        $this->sectionName = $sectionName;
    }

    public static function getRootConfigBlock($client, $sectionName)
    {
        $config = $client->get('/api/haproxy/settings/get');
        $data = $config['haproxy'][$sectionName] ?? [];
        return new self($client, $data, $sectionName);
    }

    public static function getInstalledPackagesConfigBlock($client, $sectionName)
    {
        $config = $client->get('/api/haproxy/settings/get');
        $data = $config['haproxy']['installed_packages'][$sectionName] ?? [];
        return new self($client, $data, $sectionName);
    }

    public function save()
    {
        // This will be implemented later
    }
}
