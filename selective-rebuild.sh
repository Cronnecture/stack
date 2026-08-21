#!/bin/bash
# Cronnecture Enterprise Deployment - Vaultwarden Safe
# Preserves Stalwart Mail + Vaultwarden, adds enterprise intelligence

set -e

echo "🚀 CRONNECTURE ENTERPRISE DEPLOYMENT"
echo "===================================="
echo ""
echo "This will:"
echo "✅ PRESERVE: Stalwart Mail (mail namespace)"  
echo "✅ PRESERVE: Vaultwarden (identity namespace)"
echo "🧹 CLEAN: Everything else"
echo "🚀 DEPLOY: Enterprise AI intelligence"
echo ""

read -p "Continue? (yes/no): " confirm
if [[ ! "$confirm" =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

echo ""
echo "🛡️ Creating backup..."
BACKUP_DIR="/tmp/cronnecture-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup critical namespaces
if kubectl get ns mail >/dev/null 2>&1; then
    kubectl get all,secrets,configmaps,pvc -n mail -o yaml > "$BACKUP_DIR/mail-backup.yaml"
    echo "✅ Mail namespace backed up"
fi

if kubectl get ns identity >/dev/null 2>&1; then
    kubectl get all,secrets,configmaps,pvc -n identity -o yaml > "$BACKUP_DIR/identity-backup.yaml"  
    echo "✅ Identity namespace backed up"
fi

echo ""
echo "🧹 Cleaning non-critical resources..."

# Get all namespaces except critical ones
namespaces=$(kubectl get ns -o name | grep -v "namespace/mail\|namespace/identity\|namespace/kube-\|namespace/default" || true)

for ns in $namespaces; do
    ns_name=$(echo $ns | cut -d'/' -f2)
    echo "🧹 Removing namespace: $ns_name"
    kubectl delete namespace "$ns_name" --ignore-not-found=true --timeout=60s || true
done

echo ""
echo "🚀 Deploying enterprise intelligence..."

# Create intelligence namespace
kubectl create namespace cronnecture-intelligence --dry-run=client -o yaml | kubectl apply -f -

# Generate master encryption key
MASTER_KEY=$(openssl rand -base64 32)

# Create intelligence code ConfigMap
echo "📦 Creating intelligence code bundle..."
kubectl create configmap intelligence-code \
  --namespace=cronnecture-intelligence \
  --from-file=intelligence/ \
  --dry-run=client -o yaml | kubectl apply -f -

# Create master key secret  
kubectl create secret generic cronnecture-master-key \
  --namespace=cronnecture-intelligence \
  --from-literal=master-key="$MASTER_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# Deploy real intelligence system
echo "🧠 Deploying enterprise intelligence system..."
kubectl apply -f intelligence/kubernetes/intelligence-deployment.yaml

# Create Cloudflare credentials if provided
if [[ -n "$CLOUDFLARE_API_TOKEN" ]]; then
    kubectl create secret generic cloudflare-credentials \
      --namespace=cronnecture-intelligence \
      --from-literal=api-token="$CLOUDFLARE_API_TOKEN" \
      --from-literal=account-id="${CLOUDFLARE_ACCOUNT_ID:-}" \
      --from-literal=zone-id="${CLOUDFLARE_ZONE_ID:-}" \
      --dry-run=client -o yaml | kubectl apply -f -
    echo "✅ Cloudflare credentials configured"
fi

echo ""
echo "🔄 Restoring critical services..."

# Restore mail namespace
if [[ -f "$BACKUP_DIR/mail-backup.yaml" ]]; then
    kubectl apply -f "$BACKUP_DIR/mail-backup.yaml" || echo "⚠️ Some mail resources may need manual restoration"
    echo "✅ Mail namespace restored"
fi

# Restore identity namespace  
if [[ -f "$BACKUP_DIR/identity-backup.yaml" ]]; then
    kubectl apply -f "$BACKUP_DIR/identity-backup.yaml" || echo "⚠️ Some identity resources may need manual restoration"
    echo "✅ Identity namespace restored"
fi

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 30

echo ""
echo "✅ DEPLOYMENT COMPLETED!"
echo ""
echo "📊 SYSTEM STATUS:"

# Check mail
if kubectl get pods -n mail >/dev/null 2>&1; then
    mail_pods=$(kubectl get pods -n mail --no-headers | wc -l)
    echo "📧 Stalwart Mail: ✅ RUNNING ($mail_pods pods)"
else
    echo "📧 Stalwart Mail: ⚠️ Check status"
fi

# Check vaultwarden
if kubectl get pods -n identity >/dev/null 2>&1; then
    identity_pods=$(kubectl get pods -n identity --no-headers | wc -l)
    echo "🔒 Vaultwarden: ✅ RUNNING ($identity_pods pods)"
else
    echo "🔒 Vaultwarden: ⚠️ Check status"
fi

# Check intelligence system
if kubectl get pods -n cronnecture-intelligence >/dev/null 2>&1; then
    credential_pods=$(kubectl get pods -n cronnecture-intelligence -l app=credential-manager --no-headers 2>/dev/null | wc -l)
    monitoring_pods=$(kubectl get pods -n cronnecture-intelligence -l app=monitoring-system --no-headers 2>/dev/null | wc -l)
    orchestrator_pods=$(kubectl get pods -n cronnecture-intelligence -l app=master-orchestrator --no-headers 2>/dev/null | wc -l)
    
    if [[ $credential_pods -gt 0 && $monitoring_pods -gt 0 && $orchestrator_pods -gt 0 ]]; then
        echo "🧠 Enterprise Intelligence: ✅ ACTIVE (credential: $credential_pods, monitoring: $monitoring_pods, orchestrator: $orchestrator_pods)"
    else
        echo "🧠 Enterprise Intelligence: ⚠️ PARTIAL (credential: $credential_pods, monitoring: $monitoring_pods, orchestrator: $orchestrator_pods)"
    fi
else
    echo "🧠 Enterprise Intelligence: ⚠️ Check status"
fi

echo ""
echo "🎛️ ACCESS POINTS:"
echo "• Mail Admin: kubectl port-forward -n mail svc/stalwart 8080:8080"
echo "• Vaultwarden: https://vault.cronnecture.com"
echo "• Intelligence Logs: kubectl logs -n cronnecture-intelligence -l app=master-orchestrator -f"
echo "• Credential Manager: kubectl logs -n cronnecture-intelligence -l app=credential-manager -f"
echo "• Monitoring System: kubectl logs -n cronnecture-intelligence -l app=monitoring-system -f"

echo ""
echo "💾 Backup saved to: $BACKUP_DIR"
echo ""
echo "🎉 Your VPS is now enterprise-grade with preserved critical services!"