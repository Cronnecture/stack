# Cronnecture stack root. Ansible lives in ./ansible.
STACK_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ANSIBLE_DIR := $(STACK_ROOT)/ansible
export STACK_ROOT
export ANSIBLE_DIR
export APPS_DIR=$(STACK_ROOT)/apps
export FLEET_ROOT=$(ANSIBLE_DIR)
export ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg

.PHONY: help deploy site stack baseline cluster cloudflare clients auto-heal reboot-node \
	control-plane control-plane-hot identity mail health ping ansible check check-smoke \
	marketing portfolio identity-failsafe

help:
	@echo "Cronnecture stack root: $(STACK_ROOT)"
	@echo "Ansible fleet:          $(ANSIBLE_DIR)"
	@echo "Docs:                   $(STACK_ROOT)/docs"
	@echo ""
	@echo "  make deploy           Ansible stack playbook + operator images"
	@echo "  make stack            Ansible stack playbook (no image rebuild)"
	@echo "  make site             Full Ansible converge (includes stack.yml)"
	@echo "  make control-plane      Full CP (templates manifests, including docs mount)"
	@echo "  make control-plane-hot  Fast CP image roll (code/UI only; does not change hostPaths)"
	@echo "  make check            Playbook syntax-check"
	@echo "  make check-smoke      Characterization suite (no cluster)"
	@echo "  make marketing        Build apps/marketing → cronnecture-website"
	@echo "  make portfolio        Build apps/portfolio image"
	@echo "  make cloudflare       Sync CF edge + portals"
	@echo "  make clients          Sync client tunnels"
	@echo "  make auto-heal        Watchdog --heal"
	@echo "  make reboot-node HOST=…  SSH reboot a node"
	@echo "  make identity-failsafe  Auth HA status (RB-16)"
	@echo ""
	@echo "Other Ansible targets: make -C ansible <target>   or   make <target>"

deploy:
	bash $(STACK_ROOT)/deploy.sh

check check-smoke:
	$(MAKE) -C $(ANSIBLE_DIR) $@

marketing:
	bash $(STACK_ROOT)/scripts/build-app.sh marketing

portfolio:
	bash $(STACK_ROOT)/scripts/build-app.sh portfolio

identity-failsafe:
	bash $(STACK_ROOT)/scripts/identity-failsafe.sh status

ansible:
	$(MAKE) -C $(ANSIBLE_DIR) $(ARGS)

# Forward the fleet Makefile so operators stay in /home/dev/stack.
site stack baseline cluster cloudflare clients auto-heal control-plane control-plane-hot \
identity mail health ping lockdown fleet-ops siem-teardown reboot-node isolate-node \
restart-service incident-scan:
	$(MAKE) -C $(ANSIBLE_DIR) $@
