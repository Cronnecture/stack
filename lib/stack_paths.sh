# Cronnecture stack root. Source from deploy/scripts:
#   source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/stack_paths.sh"
#
# /home/dev/stack is the operator root. Ansible lives at $STACK_ROOT/ansible.

_stack_usable() {
  local cand="${1:-}"
  [[ -n "$cand" && -d "$cand/kubernetes" && -f "$cand/deploy.sh" ]]
}

_ansible_usable() {
  local cand="${1:-}"
  [[ -n "$cand" && -d "$cand/config/inventory" && -f "$cand/ansible.cfg" ]]
}

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_ROOT="${STACK_ROOT:-}"
if ! _stack_usable "$STACK_ROOT"; then
  if _stack_usable "$_here/.."; then
    STACK_ROOT="$(cd "$_here/.." && pwd)"
  elif _stack_usable /home/dev/stack; then
    STACK_ROOT=/home/dev/stack
  else
    STACK_ROOT="$(cd "$_here/.." && pwd)"
  fi
fi
export STACK_ROOT

ANSIBLE_DIR="${ANSIBLE_DIR:-${FLEET_ROOT:-}}"
if ! _ansible_usable "$ANSIBLE_DIR"; then
  if _ansible_usable "$STACK_ROOT/ansible"; then
    ANSIBLE_DIR="$STACK_ROOT/ansible"
  elif _ansible_usable /home/dev/stack/ansible; then
    ANSIBLE_DIR=/home/dev/stack/ansible
  else
    ANSIBLE_DIR="$STACK_ROOT/ansible"
  fi
fi
export ANSIBLE_DIR
export APPS_DIR="${APPS_DIR:-$STACK_ROOT/apps}"
export DOCS_DIR="${DOCS_DIR:-$STACK_ROOT/docs}"
export FLEET_ROOT="${FLEET_ROOT:-$ANSIBLE_DIR}"
if ! _ansible_usable "$FLEET_ROOT"; then
  export FLEET_ROOT="$ANSIBLE_DIR"
fi
export ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-$ANSIBLE_DIR/ansible.cfg}"
export ANSIBLE_VAULT_FILE="${ANSIBLE_VAULT_FILE:-$ANSIBLE_DIR/config/inventory/group_vars/all/vault.yml}"
export ANSIBLE_VAULT_PASSWORD_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$HOME/.ansible/vault_pass}"

unset _here
unset -f _stack_usable _ansible_usable
