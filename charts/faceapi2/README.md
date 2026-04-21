# faceapi2 Helm Chart

This chart deploys the full `faceapi2` stack:

- Flask API/dashboard
- MySQL
- MongoDB
- Mosquitto MQTT
- Face metadata publisher/subscriber
- Live match engine
- Face recognition engine
- One-shot jobs for registration and image push

## Install

Create a local secrets override file first:

```bash
cp charts/faceapi2/values.secrets.example.yaml charts/faceapi2/values.secrets.local.yaml
```

Then install with that local file:

```bash
helm install faceapi2 ./charts/faceapi2 -n faceapi2 --create-namespace -f ./charts/faceapi2/values.secrets.local.yaml
```

## Upgrade

```bash
helm upgrade --install faceapi2 ./charts/faceapi2 -n faceapi2 --create-namespace -f ./charts/faceapi2/values.secrets.local.yaml
```

## Optional local override

Create a `values.local.yaml` file for non-secret overrides and keep it out of git:

```yaml
ingress:
  enabled: true
  hosts:
    - host: faceapi2.local
      paths:
        - path: /
          pathType: Prefix

autoscaling:
  api:
    enabled: true
    minReplicas: 1
    maxReplicas: 3
```

Then install with:

```bash
helm upgrade --install faceapi2 ./charts/faceapi2 -n faceapi2 --create-namespace -f ./charts/faceapi2/values.secrets.local.yaml -f ./charts/faceapi2/values.local.yaml
```
