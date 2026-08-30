# Fleet backup architecture (control plane)

## Layers

| Layer | Role |
|--------|------|
| **R2** (`cronnecture-fleet-backups` / `fleet-backups/{stamp}/`) | Off-site catalog and disaster copies |
| **On-site cache** (`/var/backups/cronnecture-fleet/{stamp}/`) | Fast restore path; synced from R2 when needed |
| **In-memory catalog** (`backup_catalog.py`) | Instant `GET /api/backups` — no Ansible on read |
| **Reconcile worker** | Every ~120s + `POST /api/backups/reconcile` + after backup/delete |

## Backup types

- **config** — small: `cf_clients`, emergency inventory snippets  
- **etcd** — medium: snapshot log + node inventory at capture time  
- **platform** — medium: ingress/deploy exports  
- **full** — large: all of the above + identity dumps + mail + operator books + control-plane client-documents + retention prune + R2 required for job success when R2 configured  

Naming: `cronnecture-fleet-{type}-{YYYYMMDD-HHMMSS}` (UTC).

## Failsafe restore

1. **Cache on node** if bundle is R2-only  
2. **Validate** (type-aware checks)  
3. **Dry run** restore plan on control node  
4. **Apply** only after dry run (UI enforced; API blocks failed `STATUS`)  
5. **etcd / cluster** — manual RB-07 (destructive)

## Ops

```bash
make fleet-ops          # scripts + backup-r2.env on control node
make control-plane      # API + UI
```

R2 EU buckets: endpoint `…eu.r2.cloudflarestorage.com`; AWS CLI checksum env in `backup-r2.env`.

## API

- `GET /api/backups` — cached catalog  
- `POST /api/backups/reconcile` — background full rescan  
- `DELETE /api/backups/{stamp}?scope=both|onsite|r2` — evict + reconcile  
