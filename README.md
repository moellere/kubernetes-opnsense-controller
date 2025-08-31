# Kubernetes OPNsense Controller (Python Edition)

[![Docker Pulls](https://img.shields.io/docker/pulls/travisghansen/kubernetes-pfsense-controller.svg)](https://hub.docker.com/r/travisghansen/kubernetes-pfsense-controller)
[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/travisghansen/kubernetes-pfsense-controller/main.yml?branch=master&style=flat-square)](https://github.com/travisghansen/kubernetes-pfsense-controller/actions)

This project has been rewritten in Python to serve as a Kubernetes controller that works hard to keep [OPNsense](https://www.opnsense.org/) and [Kubernetes](https://kubernetes.io/) in sync and harmony. The primary focus is to facilitate a first-class Kubernetes cluster by integrating and/or implementing features that generally do not come with bare-metal installations.

This is achieved by watching the standard Kubernetes API for resource changes and sending appropriate updates to OPNsense via its REST API.

**Please note, this controller is not designed to run multiple instances simultaneously (i.e., do not increase the number of replicas).**

## Installation

The controller is designed to be run as a container within your Kubernetes cluster.

### Container Image

A `Dockerfile` is provided to build the container image.

```bash
docker build -t kubernetes-opnsense-controller .
```

### Deployment

Various example YAML files are available in the `deploy` directory of the project. You will need to adapt them to your needs and apply them with `kubectl apply`. The key components to configure are:
- A `Deployment` to run the controller.
- A `ConfigMap` to provide configuration for the controller and its plugins.
- A `ServiceAccount` and necessary RBAC permissions (`Role`, `RoleBinding`) to allow the controller to access Kubernetes API resources.

## Configuration

The controller is configured via environment variables and a `ConfigMap`.

### Environment Variables

- `OPNSENSE_URL`: The base URL for the OPNsense API (e.g., `https://opnsense.example.com/api`).
- `OPNSENSE_API_KEY`: The API key for authentication.
- `OPNSENSE_API_SECRET`: The API secret for authentication.
- `CONTROLLER_NAMESPACE`: The namespace where the controller is running and where it looks for its `ConfigMap` (default: `kube-system`).
- `CONTROLLER_CONFIGMAP`: The name of the `ConfigMap` to load configuration from (default: `kubernetes-opnsense-controller`).

### ConfigMap

A `ConfigMap` is used to enable and configure the controller's plugins. The `ConfigMap` should contain a `config.yaml` key with the plugin configuration.

**Example `config.yaml`:**
```yaml
metallb:
  enabled: true
  nodeLabelSelector:
  nodeFieldSelector:
  bgp-implementation: frr # or openbgp
  options:
    frr:
      template:
        peergroup: metallb

haproxy-declarative:
  enabled: true
```

## Plugins

The controller is comprised of several plugins. The following have been implemented in the Python version:

### MetalLB
This plugin dynamically updates BGP neighbors in OPNsense by continually monitoring cluster `Node`s. It is useful for BGP-based `LoadBalancer` implementations like MetalLB or Kube-VIP. The plugin assumes you have a BGP server (like FRR) configured in OPNsense.

### HAProxy Declarative
This plugin allows you to declaratively create HAProxy frontend and backend definitions as `ConfigMap` resources in the cluster. See `examples/declarative-example.yaml` for an example of the `ConfigMap` structure.

---

*The following plugins from the original PHP version have not yet been implemented in the Python rewrite:*
- `haproxy-ingress-proxy`
- `opnsense-dns-services`
- `opnsense-dns-ingresses`
- `opnsense-dns-haproxy-ingress-proxy`

## Development

### Prerequisites
- Python 3.8+
- `pip`

### Setup
1. Clone the repository.
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`

### Running Locally
To run the controller locally for development, ensure you have a valid `kubeconfig` file and set the required environment variables (e.g., in a `.env` file).

```bash
# Make sure your KUBECONFIG environment variable is pointing to your cluster
# and set the OPNsense credentials in a .env file.
python src/main.py
```

### Running Tests
To run the unit tests:
```bash
python -m unittest discover tests
```
