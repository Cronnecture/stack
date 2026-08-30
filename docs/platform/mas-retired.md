# MAS — retired

Cronnecture MAS (LangGraph host process, Jarvis HUD at `/` and `/ai`, leftover `/api/mas` and `/api/v1/ai`) is **removed**.

Operators use **https://control.cronnecture.com**. Repair is host `incident-watchdog` (`make auto-heal`) and leftover `/api/selfheal`. Python MAS/Jarvis modules are deleted from the control-plane image; catalog `retired_prefixes` still 501 `/api/v1/ai` and `/api/mas`.

A leftover host unit can be stopped with `ansible-playbook playbooks/mas.yml` (uninstall only). Host data under `/var/lib/cronnecture/mas` was **deleted 2026-08-27**.
