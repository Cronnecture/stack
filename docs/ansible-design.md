# Ansible Automation Playbooks

## Overview
Infrastructure as Code using Ansible for configuration management, deployment automation, and operational tasks.

## Playbook Structure
```yaml
playbooks/
├── site.yml                 # Main orchestration
├── client-onboarding/
│   ├── create-namespace.yml
│   ├── deploy-application.yml
│   └── configure-monitoring.yml
├── maintenance/
│   ├── ssl-renewal.yml
│   ├── backup-data.yml
│   └── security-updates.yml
├── incident-response/
│   ├── restart-services.yml
│   ├── rollback-deployment.yml
│   └── failover-database.yml
└── billing/
    ├── provision-resources.yml
    ├── update-usage-metrics.yml
    └── suspend-services.yml
```

## Client Onboarding Playbook
```yaml
---
- name: Deploy new client project
  hosts: kubernetes_master
  vars:
    client_name: "{{ client_name }}"
    service_tier: "{{ service_tier }}"  # website|webshop|portal
    domain: "{{ domain }}"
    
  tasks:
  - name: Create client namespace
    kubernetes.core.k8s:
      name: "client-{{ client_name }}"
      api_version: v1
      kind: Namespace
      state: present
      
  - name: Apply resource quotas
    kubernetes.core.k8s:
      definition:
        apiVersion: v1
        kind: ResourceQuota
        metadata:
          name: "{{ client_name }}-quota"
          namespace: "client-{{ client_name }}"
        spec: "{{ quotas[service_tier] }}"
        
  - name: Deploy application from template
    kubernetes.core.k8s:
      definition: "{{ lookup('template', 'templates/' + service_tier + '.j2') }}"
      
  - name: Configure DNS record
    community.dns.cloudflare_dns:
      zone: "{{ dns_zone }}"
      record: "{{ domain }}"
      type: A
      value: "{{ ingress_ip }}"
      
  - name: Setup monitoring
    kubernetes.core.k8s:
      definition: "{{ lookup('template', 'monitoring/servicemonitor.j2') }}"
      
  - name: Initialize backup schedule
    kubernetes.core.k8s:
      definition: "{{ lookup('template', 'backup/cronjob.j2') }}"
```

## Incident Response Playbook
```yaml
---
- name: Automated incident response
  hosts: kubernetes_master
  vars:
    incident_type: "{{ incident_type }}"
    client_name: "{{ client_name }}"
    
  tasks:
  - name: Restart failed pods
    when: incident_type == "pod_crash"
    kubernetes.core.k8s:
      api_version: v1
      kind: Pod
      namespace: "client-{{ client_name }}"
      label_selectors:
        - app={{ client_name }}
      state: absent
      
  - name: Scale up replicas for high load
    when: incident_type == "high_load"
    kubernetes.core.k8s:
      api_version: apps/v1
      kind: Deployment
      name: "{{ client_name }}-app"
      namespace: "client-{{ client_name }}"
      definition:
        spec:
          replicas: "{{ current_replicas * 2 }}"
          
  - name: Rollback deployment
    when: incident_type == "bad_deployment"
    shell: |
      kubectl rollout undo deployment/{{ client_name }}-app -n client-{{ client_name }}
      
  - name: Notify via WhatsApp
    uri:
      url: "{{ whatsapp_webhook_url }}"
      method: POST
      body_format: json
      body:
        message: "Incident {{ incident_type }} resolved for {{ client_name }}"
```

## Maintenance Automation
```yaml
---
- name: Daily maintenance tasks
  hosts: kubernetes_master
  schedule: "0 2 * * *"  # 2 AM daily
  
  tasks:
  - name: Backup client databases
    kubernetes.core.k8s_exec:
      namespace: "{{ item }}"
      pod: "{{ item }}-db-0"
      command: |
        pg_dump {{ db_name }} | gzip > /backups/{{ ansible_date_time.date }}.sql.gz
    loop: "{{ client_namespaces }}"
    
  - name: Cleanup old logs
    shell: |
      find /var/log/containers -name "*.log" -mtime +7 -delete
      
  - name: Update SSL certificates
    kubernetes.core.k8s:
      api_version: v1
      kind: Secret
      namespace: cert-manager
      name: letsencrypt-prod
      state: present
```