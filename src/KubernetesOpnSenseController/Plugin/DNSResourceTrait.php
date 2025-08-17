<?php

namespace KubernetesPfSenseController\Plugin;

/**
 * Common code for DNS plugins
 *
 * Trait DNSResourceTrait
 * @package KubernetesPfSenseController\Plugin
 */
trait DNSResourceTrait
{
    /**
     * Update pfSense state
     *
     * @return bool
     */
    public function doAction()
    {
        $pluginConfig = $this->getConfig();
        $dnsmasqEnabled = $pluginConfig['dnsBackends']['dnsmasq']['enabled'];
        $unboundEnabled = $pluginConfig['dnsBackends']['unbound']['enabled'];

        // only supported options move along
        if (!$dnsmasqEnabled && !$unboundEnabled) {
            $this->log('plugin enabled without valid dnsBackends');
            return true;
        }

        $resourceHosts = [];
        foreach ($this->state['resources'] as $resource) {
            $this->buildResourceHosts($resourceHosts, $resource);
        }

        $hosts = [];
        $managedHostsPreSave = [];
        foreach ($resourceHosts as $hostName => $struct) {
            $ip = $struct['ip'];
            $this->log("setting hostname entry: Host - {$hostName}, IP - {$ip}");
            $managedHostsPreSave[$hostName] = [
                'resource' => $this->getKubernetesResourceDetails($struct['resource']),
            ];
            $hosts[] = [
                'host' => explode('.', $hostName, 2)[0],
                'domain' => explode('.', $hostName, 2)[1],
                'ip' => $ip,
                'descr' => 'created by kpc - do not edit',
                'aliases' => '',
            ];
        }

        try {
            $client = $this->getController()->getRegistryItem('opnSenseClient');

            if ($dnsmasqEnabled) {
                $existingHosts = $client->get('/api/dnsmasq/settings/search_host');
                $existingHostsByName = [];
                foreach ($existingHosts['rows'] as $row) {
                    $existingHostsByName[$row['hostname']] = $row;
                }

                foreach ($hosts as $host) {
                    $hostname = $host['host'] . '.' . $host['domain'];
                    if (isset($existingHostsByName[$hostname])) {
                        // update
                        $uuid = $existingHostsByName[$hostname]['uuid'];
                        $client->post('/api/dnsmasq/settings/set_host/' . $uuid, ['host' => $host]);
                        unset($existingHostsByName[$hostname]);
                    } else {
                        // add
                        $client->post('/api/dnsmasq/settings/add_host', ['host' => $host]);
                    }
                }

                foreach ($toDeleteHosts as $hostName) {
                    if (isset($existingHostsByName[$hostName])) {
                        $uuid = $existingHostsByName[$hostName]['uuid'];
                        $client->post('/api/dnsmasq/settings/del_host/' . $uuid);
                    }
                }

                $this->reloadDnsmasq();
            }

            if ($unboundEnabled) {
                $existingHosts = $client->get('/api/unbound/settings/search_host_override');
                $existingHostsByName = [];
                foreach ($existingHosts['rows'] as $row) {
                    $existingHostsByName[$row['hostname']] = $row;
                }

                foreach ($hosts as $host) {
                    $hostname = $host['host'] . '.' . $host['domain'];
                    if (isset($existingHostsByName[$hostname])) {
                        // update
                        $uuid = $existingHostsByName[$hostname]['uuid'];
                        $client->post('/api/unbound/settings/set_host_override/' . $uuid, ['host' => $host]);
                        unset($existingHostsByName[$hostname]);
                    } else {
                        // add
                        $client->post('/api/unbound/settings/add_host_override', ['host' => $host]);
                    }
                }

                foreach ($toDeleteHosts as $hostName) {
                    if (isset($existingHostsByName[$hostName])) {
                        $uuid = $existingHostsByName[$hostName]['uuid'];
                        $client->post('/api/unbound/settings/del_host_override/' . $uuid);
                    }
                }

                $this->reloadUnbound();
            }

            // save data to store
            $store['managed_hosts'] = $managedHostsPreSave;
            $this->saveStore($store);

            return true;
        } catch (\Exception $e) {
            $this->log('failed update/reload: '.$e->getMessage().' ('.$e->getCode().')');
            return false;
        }
    }

    /**
     * Does a sanity check to prevent over-aggressive updates when watch resources are technically
     * modified but the things we care about are not
     *
     * @param $event
     * @param $oldItem
     * @param $item
     * @param $stateKey
     * @param $options
     * @return bool
     */
    public function shouldTriggerFromWatchUpdate($event, $oldItem, $item, $stateKey, $options = [])
    {
        if ($stateKey == "resources") {
            // will be NULL for ADDED and DELETED
            if ($oldItem === null) {
                $tmpResourceHosts = [];
                switch ($event['type']) {
                    case "ADDED":
                    case "DELETED":
                        $this->buildResourceHosts($tmpResourceHosts, $item);
                        if (count($tmpResourceHosts) > 0) {
                            return true;
                        }
                        break;
                }

                return false;
            }

            $oldResourceHosts = [];
            $newResourceHosts = [];

            $this->buildResourceHosts($oldResourceHosts, $oldItem);
            $this->buildResourceHosts($newResourceHosts, $item);

            foreach ($oldResourceHosts as $host => $value) {
                $oldResourceHosts[$host] = ['ip' => $value['ip']];
            }

            foreach ($newResourceHosts as $host => $value) {
                $newResourceHosts[$host] = ['ip' => $value['ip']];
            }

            if (md5(json_encode($oldResourceHosts)) != md5(json_encode($newResourceHosts))) {
                return true;
            }

            return false;
        }

        return false;
    }
}
