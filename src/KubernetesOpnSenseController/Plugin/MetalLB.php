<?php

namespace KubernetesOPNSenseController\Plugin;

/**
 * Purpose of plugin is to sync cluster node changes to the appropriate bgp implementation configuration.
 *
 * Class MetalLb
 * @package KubernetesOPNSenseController\Plugin
 */
use KubernetesOpnSenseController\Plugin\OpnSenseAbstract;

class MetalLB extends OpnSenseAbstract
{
    use CommonTrait;
    /**
     * Unique plugin ID
     */
    public const PLUGIN_ID = 'metallb';

    /**
     * Init the plugin
     *
     * @throws \Exception
     */
    public function init()
    {
        $controller = $this->getController();
        $pluginConfig = $this->getConfig();
        $nodeLabelSelector = $pluginConfig['nodeLabelSelector'] ?? null;
        $nodeFieldSelector = $pluginConfig['nodeFieldSelector'] ?? null;

        // initial load of nodes
        $params = [
            'labelSelector' => $nodeLabelSelector,
            'fieldSelector' => $nodeFieldSelector,
        ];
        $nodes = $controller->getKubernetesClient()->createList('/api/v1/nodes', $params)->get();
        $this->state['nodes'] = $nodes['items'];

        // watch for node changes
        $params = [
            'labelSelector' => $nodeLabelSelector,
            'fieldSelector' => $nodeFieldSelector,
            'resourceVersion' => $nodes['metadata']['resourceVersion'],
        ];
        $watch = $controller->getKubernetesClient()->createWatch('/api/v1/watch/nodes', $params, $this->getNodeWatchCallback('nodes'));
        $this->addWatch($watch);
        $this->delayedAction();
    }

    /**
     * Deinit the plugin
     */
    public function deinit()
    {
    }

    /**
     * Pre read watches
     */
    public function preReadWatches()
    {
    }

    /**
     * Post read watches
     */
    public function postReadWatches()
    {
    }

    /**
     * Update OPNSense state
     *
     * @return bool
     */
    public function doAction()
    {
        $pluginConfig = $this->getConfig();

        switch ($pluginConfig['bgp-implementation']) {
            case 'openbgp':
            case 'frr':
                return $this->doActionGeneric();
                break;
            default:
                $this->log('unsupported bgp-implementation: '.$pluginConfig['bgp-implementation']);
                return false;
                break;
        }
    }

    /**
     * Update OPNSense state for bgp implementation
     *
     * @return bool
     */
    private function doActionGeneric()
    {
        $pluginConfig = $this->getConfig();
        $client = $this->getController()->getRegistryItem('opnSenseClient');

        $nodes = $this->state['nodes'];
        $desiredNeighbors = [];
        $managedNeighborsPreSave = [];
        foreach ($nodes as $node) {
            $host = 'kpc-'.KubernetesUtils::getNodeIp($node);
            $managedNeighborsPreSave[$host] = [
                'resource' => $this->getKubernetesResourceDetails($node),
            ];
            $neighbor = $pluginConfig['options'][$pluginConfig['bgp-implementation']]['template'];
            $neighbor['address'] = KubernetesUtils::getNodeIp($node);
            $neighbor['description'] = $host;
            $desiredNeighbors[$host] = $neighbor;
        }

        $existingNeighbors = [];
        $endpoint = '';
        switch ($pluginConfig['bgp-implementation']) {
            case 'openbgp':
                $endpoint = '/api/openbgpd/settings/search_neighbor';
                break;
            case 'frr':
                $endpoint = '/api/frr/settings/search_bgp_neighbor';
                break;
        }
        $response = $client->get($endpoint);
        foreach($response['rows'] as $row) {
            $existingNeighbors[$row['description']] = $row;
        }

        // Add/update neighbors
        foreach ($desiredNeighbors as $host => $neighbor) {
            if (isset($existingNeighbors[$host])) {
                // update
                $uuid = $existingNeighbors[$host]['uuid'];
                $client->post(str_replace('search', 'set', $endpoint) . '/' . $uuid, ['neighbor' => $neighbor]);
                unset($existingNeighbors[$host]);
            } else {
                // add
                $client->post(str_replace('search', 'add', $endpoint), ['neighbor' => $neighbor]);
            }
        }

        // Delete neighbors
        foreach ($existingNeighbors as $host => $neighbor) {
            $uuid = $neighbor['uuid'];
            $client->post(str_replace('search', 'del', $endpoint) . '/' . $uuid);
        }


        // save newly managed configuration
        try {
            switch ($pluginConfig['bgp-implementation']) {
                case 'openbgp':
                    $this->reloadOpenbgp();
                    break;
                case 'frr':
                    $this->reloadFrrBgp();
                    break;
            }
            $store = $this->getStore();
            if (empty($store)) {
                $store = [];
            }
            $store[$pluginConfig['bgp-implementation']]['managed_neighbors'] = $managedNeighborsPreSave;
            $this->saveStore($store);

            return true;
        } catch (\Exception $e) {
            $this->log('failed update/reload: '.$e->getMessage().' ('.$e->getCode().')');
            return false;
        }
    }
}
