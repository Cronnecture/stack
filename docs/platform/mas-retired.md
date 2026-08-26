# MAS — retired

Cronnecture MAS (LangGraph host process, Jarvis HUD at `/` and `/ai`, leftover `/api/mas` and `/api/v1/ai`) is **removed**.

Operators use **https://ops.cronnecture.com/app/**. Repair is host `incident-watchdog` (`make auto-heal`) and leftover `/api/selfheal`. Ansible + Kubernetes are unchanged.

A leftover host unit can be stopped with `ansible-playbook playbooks/mas.yml` (uninstall only). Data under `/var/lib/cronnecture/mas` is left on disk.
