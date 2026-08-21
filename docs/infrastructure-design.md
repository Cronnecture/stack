# Infrastructure - Kubernetes & Ansible Automation

## Overview
Automated infrastructure provisioning and management using Kubernetes for container orchestration and Ansible for configuration management.

## Architecture

### Kubernetes Cluster Structure
```yaml
# Namespace organization
namespaces:
  - cronnecture-system    # Core agents and services
  - cronnecture-clients   # Client websites/webshops/portals
  - cronnecture-monitoring # Monitoring stack
  - cronnecture-billing   # Billing and payment services

# Resource quotas per service tier
website_quota:
  requests.cpu: "100m"
  requests.memory: "128Mi" 
  limits.cpu: "500m"
  limits.memory: "512Mi"

webshop_quota:
  requests.cpu: "200m"
  requests.memory: "256Mi"
  limits.cpu: "1000m" 
  limits.memory: "1Gi"

portal_quota:
  requests.cpu: "500m"
  requests.memory: "512Mi"
  limits.cpu: "2000m"
  limits.memory: "4Gi"
```

### Client Deployment Template
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ client_name }}-{{ service_type }}
  namespace: cronnecture-clients
spec:
  replicas: {{ replica_count }}
  selector:
    matchLabels:
      app: {{ client_name }}
      tier: {{ service_type }}
  template:
    metadata:
      labels:
        app: {{ client_name }}
        tier: {{ service_type }}
        client: {{ client_name }}
    spec:
      containers:
      - name: app
        image: {{ image_registry }}/{{ template_image }}:{{ version }}
        resources:
          requests:
            cpu: {{ cpu_request }}
            memory: {{ memory_request }}
          limits:
            cpu: {{ cpu_limit }}
            memory: {{ memory_limit }}
        env:
        - name: CLIENT_CONFIG
          valueFrom:
            configMapKeyRef:
              name: {{ client_name }}-config
              key: app.yaml
---
apiVersion: v1
kind: Service
metadata:
  name: {{ client_name }}-service
  namespace: cronnecture-clients
spec:
  selector:
    app: {{ client_name }}
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ client_name }}-ingress
  namespace: cronnecture-clients
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - {{ domain }}
    secretName: {{ client_name }}-tls
  rules:
  - host: {{ domain }}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {{ client_name }}-service
            port:
              number: 80
```

## Automation Workflows

### Client Onboarding
1. Agent generates K8s manifests from templates
2. Ansible provisions DNS records
3. Deploy application with cert-manager for SSL
4. Configure monitoring and backups
5. Update billing system

### Scaling & Updates  
1. Monitor resource usage
2. Auto-scale based on traffic
3. Blue/green deployments for updates
4. Rollback capability on failures

### Disaster Recovery
1. Daily backups to object storage
2. Cross-region cluster replication
3. Automated failover procedures
4. RTO: 15 minutes, RPO: 1 hour