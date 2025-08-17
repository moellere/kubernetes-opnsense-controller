<?php

// prevent double logging
ini_set('log_errors', 1);
ini_set('display_errors', 0);

// include autoloader
require_once 'vendor/autoload.php';

// environment variable processing
if (file_exists(__DIR__.DIRECTORY_SEPARATOR.'.env')) {
    $dotenv = new Dotenv\Dotenv(__DIR__);
} else {
    $file = tempnam(sys_get_temp_dir(), 'pfsense-controller');
    register_shutdown_function(function () use ($file) {
        if (file_exists($file)) {
            unlink($file);
        }
    });

    $dotenv = new Dotenv\Dotenv(dirname($file), basename($file));
}
$dotenv->load();
$dotenv->required(['OPNSENSE_URL', 'OPNSENSE_API_KEY', 'OPNSENSE_API_SECRET'])->notEmpty();

// kubernetes client
if (getenv('KUBERNETES_SERVICE_HOST')) {
    $config = KubernetesClient\Config::InClusterConfig();
} else {
    $config = KubernetesClient\Config::BuildConfigFromFile();
}
$kubernetesClient = new KubernetesClient\Client($config);

// OPNsense client
$opnSenseClient = new \KubernetesOpnSenseController\Client(
    getenv('OPNSENSE_URL'),
    getenv('OPNSENSE_API_KEY'),
    getenv('OPNSENSE_API_SECRET')
);

// setup controller
if (getenv('CONTROLLER_NAME')) {
    $controllerName = getenv('CONTROLLER_NAME');
} else {
    $controllerName = 'kubernetes-pfsense-controller';
}

if (getenv('CONTROLLER_NAMESPACE')) {
    $controllerNamespace = getenv('CONTROLLER_NAMESPACE');
} else {
    $controllerNamespace = 'kube-system';
}


$options = [
    'configMapNamespace' => $controllerNamespace,
    //'configMapName' => $controllerName.'-controller-config',
    //'storeEnabled' => true,
    'storeNamespace' => $controllerNamespace,
    //'storeName' => $controllerName.'-controller-store',
];

// expose the above

$controller = new KubernetesPfSenseController\Controller($controllerName, $kubernetesClient, $options);
$kubernetesClient = $controller->getKubernetesClient();

// register opnSenseClient
$controller->setRegistryItem('opnSenseClient', $opnSenseClient);

// register kubernetes version info
$kubernetesVersionInfo = $kubernetesClient->request("/version");
$controller->setRegistryItem('kubernetesVersionInfo', $kubernetesVersionInfo);

// plugins
$controller->registerPlugin('\KubernetesPfSenseController\Plugin\MetalLB');
$controller->registerPlugin('\KubernetesPfSenseController\Plugin\HAProxyDeclarative');
$controller->registerPlugin('\KubernetesPfSenseController\Plugin\HAProxyIngressProxy');
$controller->registerPlugin('\KubernetesPfSenseController\Plugin\DNSHAProxyIngressProxy');
$controller->registerPlugin('\KubernetesPfSenseController\Plugin\DNSServices');
$controller->registerPlugin('\KubernetesPfSenseController\Plugin\DNSIngresses');

// start
$controller->main();
