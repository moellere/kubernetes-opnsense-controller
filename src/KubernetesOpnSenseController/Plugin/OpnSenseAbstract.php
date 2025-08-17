<?php

namespace KubernetesOpnSenseController\Plugin;

abstract class OpnSenseAbstract extends \KubernetesController\Plugin\AbstractPlugin
{
    public function reloadHAProxy()
    {
        $opnSenseClient = $this->getController()->getRegistryItem('opnSenseClient');
        try {
            $opnSenseClient->post('/api/haproxy/service/reload');
            $this->log('successfully reloaded HAProxy service');
        } catch (\Exception $e) {
            $this->log('failed reload HAProxy service: '.$e->getMessage().' ('.$e->getCode().')');
            throw $e;
        }
    }

    protected function reloadUnbound()
    {
        $opnSenseClient = $this->getController()->getRegistryItem('opnSenseClient');
        try {
            // OPNsense uses a different service name for unbound
            $opnSenseClient->post('/api/unbound/service/reload');
            $this->log('successfully reloaded unbound service');
        } catch (\Exception $e) {
            $this->log('failed reload unbound service: '.$e->getMessage().' ('.$e->getCode().')');
            throw $e;
        }
    }

    protected function reloadDnsmasq()
    {
        $opnSenseClient = $this->getController()->getRegistryItem('opnSenseClient');
        try {
            $opnSenseClient->post('/api/dnsmasq/service/reload');
            $this->log('successfully reloaded dnsmasq service');
        } catch (\Exception $e) {
            $this->log('failed reload dnsmasq service: '.$e->getMessage().' ('.$e->getCode().')');
            throw $e;
        }
    }

    protected function reloadFrrBgp()
    {
        $opnSenseClient = $this->getController()->getRegistryItem('opnSenseClient');
        try {
            $opnSenseClient->post('/api/frr/service/reload');
            $this->log('successfully reloaded frr bgp service');
        } catch (\Exception $e) {
            $this->log('failed reload frr bgp service: '.$e->getMessage().' ('.$e->getCode().')');
            throw $e;
        }
    }

    protected function reloadOpenbgp()
    {
        $opnSenseClient = $this->getController()->getRegistryItem('opnSenseClient');
        try {
            $opnSenseClient->post('/api/openbgpd/service/reload');
            $this->log('successfully reloaded openbgp service');
        } catch (\Exception $e) {
            $this->log('failed reload openbgp service: '.$e->getMessage().' ('.$e->getCode().')');
            throw $e;
        }
    }
}
