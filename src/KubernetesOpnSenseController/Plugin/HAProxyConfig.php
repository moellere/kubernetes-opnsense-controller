<?php

namespace KubernetesOpnSenseController\Plugin;

class HAProxyConfig extends ConfigBlock
{
    private $client;

    public function __construct($client)
    {
        $this->client = $client;
    }

    public static function getInstalledPackagesConfigBlock($client, $sectionName)
    {
        // This is a factory method that returns an instance of this class.
        // The sectionName is not used in the OPNsense API.
        return new self($client);
    }

    public function getFrontends()
    {
        return $this->client->get('/api/haproxy/settings/search_frontends');
    }

    public function getFrontend($name)
    {
        $frontends = $this->getFrontends();
        foreach ($frontends['rows'] as $frontend) {
            if ($frontend['name'] == $name) {
                $f = $this->client->get('/api/haproxy/settings/get_frontend/' . $frontend['uuid']);
                return $f['frontend'];
            }
        }
        return null;
    }

    public function frontendExists($name)
    {
        return $this->getFrontend($name) !== null;
    }

    public function putFrontend($frontend)
    {
        $existingFrontend = $this->getFrontend($frontend['name']);
        if ($existingFrontend) {
            $this->client->post('/api/haproxy/settings/set_frontend/' . $existingFrontend['frontend']['uuid'], ['frontend' => $frontend]);
        } else {
            $this->client->post('/api/haproxy/settings/add_frontend', ['frontend' => $frontend]);
        }
    }

    public function removeFrontend($name)
    {
        $existingFrontend = $this->getFrontend($name);
        if ($existingFrontend) {
            $this->client->post('/api/haproxy/settings/del_frontend/' . $existingFrontend['frontend']['uuid']);
        }
    }

    public function getBackends()
    {
        return $this->client->get('/api/haproxy/settings/search_backends');
    }

    public function getBackend($name)
    {
        $backends = $this->getBackends();
        foreach ($backends['rows'] as $backend) {
            if ($backend['name'] == $name) {
                return $this->client->get('/api/haproxy/settings/get_backend/' . $backend['uuid']);
            }
        }
        return null;
    }

    public function backendExists($name)
    {
        return $this->getBackend($name) !== null;
    }

    public function putBackend($backend)
    {
        $existingBackend = $this->getBackend($backend['name']);
        if ($existingBackend) {
            $this->client->post('/api/haproxy/settings/set_backend/' . $existingBackend['backend']['uuid'], ['backend' => $backend]);
        } else {
            $this->client->post('/api/haproxy/settings/add_backend', ['backend' => $backend]);
        }
    }

    public function removeBackend($name)
    {
        $existingBackend = $this->getBackend($name);
        if ($existingBackend) {
            $this->client->post('/api/haproxy/settings/del_backend/' . $existingBackend['backend']['uuid']);
        }
    }

    public function getAcls()
    {
        return $this->client->get('/api/haproxy/settings/search_acls');
    }

    public function getAcl($name)
    {
        $acls = $this->getAcls();
        foreach ($acls['rows'] as $acl) {
            if ($acl['name'] == $name) {
                return $this->client->get('/api/haproxy/settings/get_acl/' . $acl['uuid']);
            }
        }
        return null;
    }

    public function aclExists($name)
    {
        return $this->getAcl($name) !== null;
    }

    public function putAcl($acl)
    {
        $existingAcl = $this->getAcl($acl['name']);
        if ($existingAcl) {
            $this->client->post('/api/haproxy/settings/set_acl/' . $existingAcl['acl']['uuid'], ['acl' => $acl]);
        } else {
            $this->client->post('/api/haproxy/settings/add_acl', ['acl' => $acl]);
        }
    }

    public function removeAcl($name)
    {
        $existingAcl = $this->getAcl($name);
        if ($existingAcl) {
            $this->client->post('/api/haproxy/settings/del_acl/' . $existingAcl['acl']['uuid']);
        }
    }

    public function getActions()
    {
        return $this->client->get('/api/haproxy/settings/search_actions');
    }

    public function getAction($name)
    {
        $actions = $this->getActions();
        foreach ($actions['rows'] as $action) {
            if ($action['name'] == $name) {
                return $this->client->get('/api/haproxy/settings/get_action/' . $action['uuid']);
            }
        }
        return null;
    }

    public function actionExists($name)
    {
        return $this->getAction($name) !== null;
    }

    public function putAction($action)
    {
        $existingAction = $this->getAction($action['name']);
        if ($existingAction) {
            $this->client->post('/api/haproxy/settings/set_action/' . $existingAction['action']['uuid'], ['action' => $action]);
        } else {
            $this->client->post('/api/haproxy/settings/add_action', ['action' => $action]);
        }
    }

    public function removeAction($name)
    {
        $existingAction = $this->getAction($name);
        if ($existingAction) {
            $this->client->post('/api/haproxy/settings/del_action/' . $existingAction['action']['uuid']);
        }
    }
}
