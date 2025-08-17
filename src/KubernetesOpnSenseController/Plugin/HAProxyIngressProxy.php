<?php

namespace KubernetesPfSenseController\Plugin;

/**
 * Purpose of this plugin is to create a mirrored configuration of HAProxy running on pfSense to the provided ingress
 * controller already running (likely on NodePort or as a LoadBalancer) in the cluster.  The idea is that pfSense
 * running HAProxy receives traffic external to the cluster, forwards it to an existing ingress, which forwards it to
 * the appropriate pods.
 *
 * The following pre-requesites are assumed:
 *  - HAProxy Frontend (shared) already exists (configuration parameter)
 *  - HAProxy Backend already exists (configuration parameter) (this could be exposed using the Declarative plugin)
 *   - Backend should be running an exposed ingress already via NodePort or LoadBalancer (ie: nginx, haproxy, traefik)
 *
 * You may override the defaultFrontend and defaultBackend values on a per-ingress basis with annotations set on the
 * ingress:
 * haproxy-ingress-proxy.pfsense.org/frontend: test
 * haproxy-ingress-proxy.pfsense.org/backend: test
 *
 * Class HAProxyIngressProxy
 * @package KubernetesPfSenseController\Plugin
 */
use KubernetesOpnSenseController\Plugin\OpnSenseAbstract;

class HAProxyIngressProxy extends OpnSenseAbstract
{
    use CommonTrait;
    /**
     * Unique plugin ID
     */
    public const PLUGIN_ID = 'haproxy-ingress-proxy';

    /**
     * Annotation to override default frontend
     */
    public const FRONTEND_ANNOTATION_NAME = 'haproxy-ingress-proxy.opnsense.org/frontend';

    /**
     * Annotation to specific shared frontend template data
     */
    public const FRONTEND_DEFINITION_TEMPLATE_ANNOTATION_NAME = 'haproxy-ingress-proxy.opnsense.org/frontendDefinitionTemplate';

    /**
     * Annotation to override default backend
     */
    public const BACKEND_ANNOTATION_NAME = 'haproxy-ingress-proxy.opnsense.org/backend';

    /**
     * Annotation to override default enabled
     */
    public const ENABLED_ANNOTATION_NAME = 'haproxy-ingress-proxy.opnsense.org/enabled';

    /**
     * Init the plugin
     *
     * @throws \Exception
     */
    public function init()
    {
        $controller = $this->getController();
        $pluginConfig = $this->getConfig();
        $ingressLabelSelector = $pluginConfig['ingressLabelSelector'] ?? null;
        $ingressFieldSelector = $pluginConfig['ingressFieldSelector'] ?? null;

        // 1.20 will kill the old version
        // https://kubernetes.io/blog/2019/07/18/api-deprecations-in-1-16/
        $kubernetesMajorMinor = $controller->getKubernetesVersionMajorMinor();
        if (\Composer\Semver\Comparator::greaterThanOrEqualTo($kubernetesMajorMinor, '1.19')) {
            $ingressResourcePath = '/apis/networking.k8s.io/v1/ingresses';
            $ingressResourceWatchPath = '/apis/networking.k8s.io/v1/watch/ingresses';
        } elseif (\Composer\Semver\Comparator::greaterThanOrEqualTo($kubernetesMajorMinor, '1.14')) {
            $ingressResourcePath = '/apis/networking.k8s.io/v1beta1/ingresses';
            $ingressResourceWatchPath = '/apis/networking.k8s.io/v1beta1/watch/ingresses';
        } else {
            $ingressResourcePath = '/apis/extensions/v1beta1/ingresses';
            $ingressResourceWatchPath = '/apis/extensions/v1beta1/watch/ingresses';
        }

        // initial load of ingresses
        $params = [
            'labelSelector' => $ingressLabelSelector,
            'fieldSelector' => $ingressFieldSelector,
        ];
        $ingresses = $controller->getKubernetesClient()->createList($ingressResourcePath, $params)->get();
        $this->state['ingresses'] = $ingresses['items'];

        // watch for ingress changes
        $params = [
            'labelSelector' => $ingressLabelSelector,
            'fieldSelector' => $ingressFieldSelector,
            'resourceVersion' => $ingresses['metadata']['resourceVersion'],
        ];
        $watch = $controller->getKubernetesClient()->createWatch($ingressResourceWatchPath, $params, $this->getWatchCallback('ingresses'));
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
     * How long to wait for watches to settle
     *
     * @return int
     */
    public function getSettleTime()
    {
        return 10;
    }

    /**
     * Update pfSense state
     *
     * @return bool
     */
    public function doAction()
    {
        $pluginConfig = $this->getConfig();
        $haProxyConfig = new HAProxyConfig($this->getController()->getRegistryItem('opnSenseClient'));

        $resources = [];
        $frontendWarning = [];
        $backendWarning = [];
        foreach ($this->state['ingresses'] as $item) {
            $ingressNamespace = $item['metadata']['namespace'];
            $ingressName = $item['metadata']['name'];
            $frontendNameBase = $ingressNamespace . '-' . $ingressName . '-' . $this->getController()->getControllerId();

            if (KubernetesUtils::getResourceAnnotationExists($item, self::ENABLED_ANNOTATION_NAME)) {
                $ingressProxyEnabledAnnotationValue = KubernetesUtils::getResourceAnnotationValue($item, self::ENABLED_ANNOTATION_NAME);
                $ingressProxyEnabledAnnotationValue = strtolower($ingressProxyEnabledAnnotationValue);

                if (in_array($ingressProxyEnabledAnnotationValue, ["true", "1"])) {
                    $ingressProxyEnabled = true;
                } else {
                    $ingressProxyEnabled = false;
                }
            } else {
                if (key_exists('defaultEnabled', $pluginConfig)) {
                    $ingressProxyEnabled = (bool) $pluginConfig['defaultEnabled'];
                } else {
                    $ingressProxyEnabled = true;
                }
            }

            $frontendTemplate = [];
            if (KubernetesUtils::getResourceAnnotationExists($item, self::FRONTEND_DEFINITION_TEMPLATE_ANNOTATION_NAME)) {
                $frontendTemplateData = KubernetesUtils::getResourceAnnotationValue($item, self::FRONTEND_DEFINITION_TEMPLATE_ANNOTATION_NAME);
                if (!empty($frontendTemplateData)) {
                    $frontendTemplate = json_decode($frontendTemplateData, true);
                }
            }

            if (!$ingressProxyEnabled) {
                continue;
            }

            if (KubernetesUtils::getResourceAnnotationExists($item, self::FRONTEND_ANNOTATION_NAME)) {
                $primaryFrontendNames = KubernetesUtils::getResourceAnnotationValue($item, self::FRONTEND_ANNOTATION_NAME);
            } else {
                $primaryFrontendNames = $pluginConfig['defaultFrontend'];
            }

            $primaryFrontendNames = array_map('trim', explode(",", $primaryFrontendNames));

            if (KubernetesUtils::getResourceAnnotationExists($item, self::BACKEND_ANNOTATION_NAME)) {
                $backendName = KubernetesUtils::getResourceAnnotationValue($item, self::BACKEND_ANNOTATION_NAME);
            } else {
                $backendName = $pluginConfig['defaultBackend'];// use default or read annotation(s)
            }

            if (empty($primaryFrontendNames) || empty($backendName)) {
                $this->log('missing frontend or backend configuration: ' . $frontendNameBase);
                continue;
            };

            foreach ($primaryFrontendNames as $primaryFrontendName) {
                $frontendName = "{$primaryFrontendName}-{$frontendNameBase}";

                if (!$haProxyConfig->frontendExists($primaryFrontendName)) {
                    if (!in_array($primaryFrontendName, $frontendWarning)) {
                        //$frontendWarning[] = $primaryFrontendName;
                        $this->log("Frontend {$primaryFrontendName} must exist: {$frontendName}");
                    }
                    continue;
                }

                // get the type of the shared frontend
                // NOTE the below do NOT correlate 100% with what is shown on the 'type' column of the 'frontends' tab.
                // 'https' for example is actually http + ssl offloading checked
                /*
                <option value="http">http / https(offloading)</option>
                <option value="https">ssl / https(TCP mode)</option>
                <option value="tcp">tcp</option>
                */

                /**
                 * http - can do l7 rules such as headers, path, etc
                 * https - can only do sni rules
                 * tcp - cannot be used with this application
                 */
                $primaryFrontend = $haProxyConfig->getFrontend($primaryFrontendName);
                switch ($primaryFrontend['type']) {
                    case "http":
                    case "https":
                        // move along
                        break;
                    default:
                        $this->log("WARN haproxy frontend {$primaryFrontendName} has unsupported type: " . $primaryFrontend['type']);
                        continue 2;
                }

                if (!$haProxyConfig->backendExists($backendName)) {
                    if (!in_array($backendName, $backendWarning)) {
                        //$backendWarning[] = $backendName;
                        $this->log("Backend {$backendName} must exist: {$frontendName}");
                    }
                    continue;
                }

                // new frontend
                $frontend = [];
                $frontend['enabled'] = 1;
                $frontend['name'] = $frontendName;
                $frontend['description'] = 'created by kpc - do not edit';
                $frontend['bind'] = $primaryFrontend['bind'];
                $frontend['mode'] = $primaryFrontend['mode'];
                $frontend['defaultBackend'] = $backendName;
                $frontend['ssl_enabled'] = $primaryFrontend['ssl_enabled'];
                $frontend['ssl_certificates'] = $primaryFrontend['ssl_certificates'];

                $frontend['acls'] = [];
                $frontend['actions'] = [];

                foreach ($item['spec']['rules'] as $ruleKey => $rule) {
                    $aclName = $frontend['name'] . '-rule-' . $ruleKey;
                    $host = $rule['host'] ?? '';
                    if (!$this->shouldCreateRule($rule)) {
                        continue;
                    }

                    foreach ($rule['http']['paths'] as $pathKey => $path) {
                        $pathValue = $path['path'] ?? "";
                        if (empty($pathValue)) {
                            $pathValue = '/';
                        }

                        $pathType = $path['pathType'] ?? 'Prefix';

                        // new acl
                        $acl = [];
                        $acl['name'] = $aclName;

                        if (substr($host, 0, 2) == "*.") {
                            $acl['expression'] = 'hdr_reg';
                            $acl['value'] = "^[^\.]+" . str_replace([".", "-"], ["\.", "\-"], substr($host, 1)) . "(:[0-9]+)?$";
                        } else {
                            $acl['expression'] = 'hdr';
                            $acl['value'] = $host;
                        }

                        switch($pathType) {
                            case "Exact":
                                $acl['path_end'] = $pathValue;
                                break;
                            case "Prefix":
                                $acl['path_beg'] = $pathValue;
                                break;
                            case "ImplementationSpecific":
                            default:
                                $acl['path_beg'] = $pathValue;
                                break;
                        }


                        $frontend['acls'][] = $acl;

                        // new action (tied to acl)
                        $action = [];
                        $action['type'] = 'use_backend';
                        $action['use_backend'] = $backendName;
                        $action['linkedAcls'] = $aclName;

                        $frontend['actions'][] = $action;
                    }
                }

                // only create frontend if we have any actions
                if (count($frontend['actions']) > 0) {
                    // add new frontend to list of resources
                    $frontend['_resource'] = $item;
                    $resources['frontend'][] = $frontend;
                }
            }
        }

        //TODO: create certs first via ACME?

        // update config with new/updated frontends
        $managedFrontendsPreSave = [];
        $managedFrontendNamesPreSave = [];
        if (!empty($resources['frontend'])) {
            foreach ($resources['frontend'] as &$frontend) {
                // keep track of what we will manage
                $managedFrontendNamesPreSave[] = $frontend['name'];
                $managedFrontendsPreSave[$frontend['name']] = [
                    'resource' => $this->getKubernetesResourceDetails($frontend['_resource']),
                    'acls' => $frontend['acls'],
                    'actions' => $frontend['actions'],
                ];
                unset($frontend['_resource']);

                $this->log('ensuring frontend: '.$frontend['name']);
                $haProxyConfig->putFrontend($frontend);

                foreach($frontend['acls'] as $acl) {
                    $this->log('ensuring acl: '.$acl['name']);
                    $haProxyConfig->putAcl($acl);
                }

                foreach($frontend['actions'] as $action) {
                    $this->log('ensuring action: '.$action['name']);
                    $haProxyConfig->putAction($action);
                }
            }
        }

        // remove frontends created by plugin but no longer needed
        $store = $this->getStore();
        if (empty($store)) {
            $store = [];
        }

        $store['managed_frontends'] = $store['managed_frontends'] ?? [];

        // get what we currently manage
        $managedFrontendNames = @array_keys($store['managed_frontends']);
        if (empty($managedFrontendNames)) {
            $managedFrontendNames = [];
        }

        // actually remove them from config
        $toDeleteFrontends = array_diff($managedFrontendNames, $managedFrontendNamesPreSave);
        foreach ($toDeleteFrontends as $frontendName) {
            $this->log("removing frontend no longer needed: {$frontendName}");
            $haProxyConfig->removeFrontend($frontendName);
        }

        try {
            $this->reloadHAProxy();

            // persist the new set of managed frontends
            $store['managed_frontends'] = $managedFrontendsPreSave;
            $this->saveStore($store);

            return true;
        } catch (\Exception $e) {
            $this->log('failed update/reload: '.$e->getMessage().' ('.$e->getCode().')');
            return false;
        }
    }

    /**
     * If rule should be created
     *
     * @param $rule
     * @return bool
     */
    private function shouldCreateRule($rule)
    {
        $hostName = $rule['host'] ?? '';
        $pluginConfig = $this->getConfig();
        if (!empty($pluginConfig['allowedHostRegex'])) {
            $allowed = @preg_match($pluginConfig['allowedHostRegex'], $hostName);
            if ($allowed !== 1) {
                return false;
            }
        }

        return true;
    }
}
