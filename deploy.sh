#!/bin/bash
# Stack deploy goes through Ansible. This wrapper only sets roots.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/stack_paths.sh
source "$ROOT/lib/stack_paths.sh"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG STACK_ROOT ANSIBLE_DIR FLEET_ROOT ANSIBLE_CONFIG ANSIBLE_VAULT_PASSWORD_FILE

echo "== Cronnecture stack deploy (Ansible) =="
echo "STACK_ROOT=$STACK_ROOT"
echo "FLEET_ROOT=$FLEET_ROOT"

cd "$ANSIBLE_DIR"
ansible-playbook \
  -i config/inventory/hosts.ini \
  -i config/environments/production/hosts.ini \
  playbooks/stack.yml \
  -e stack_build_images=true \
  -e stack_restart_operator=true \
  "$@"

echo
echo "Stack deploy complete. Dashboard: https://control.cronnecture.com"
echo "Mail SMTP remains on host ports 25/587. HTTP is Cloudflare tunnel -> Traefik."
