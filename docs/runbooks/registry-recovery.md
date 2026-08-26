# Registry recovery

Runbook **RB-12**.

Recover container image storage after PVC loss, disk failure, or control node rebuild.

## Registry modes

| Mode | Storage | Config |
|------|---------|--------|
| **S3/R2** (production) | Cloudflare R2 bucket `cronnecture-fleet-registry` | `vault_registry_s3_*` in vault |
| **PVC** (legacy) | `fleet-registry-data` on control node | No S3 vault keys |

**Current fleet:** R2 mode (no `fleet-registry-data` PVC).

Check current mode:

```bash
sudo k3s kubectl -n platform get deploy fleet-registry -o yaml | grep -E 'REGISTRY_STORAGE|S3'
```

### R2 requires registry 3.x

Keep `control_plane_registry_image` on `registry:3.x`. R2 rejects a multipart
upload unless every part except the last is the same size, and it will not
accept a last part that is larger than the others. The 2.8 S3 driver merges its
trailing buffer into the final part, so any blob larger than twice the chunk
size (10 MB by default, so anything over ~21 MB) fails to push:

```
# registry log
unknown error completing upload: InvalidPart: All non-trailing parts must have the same length.
# client
error pushing image: failed to push to destination ...: UNKNOWN: unknown error
```

Smaller layers push fine, so this surfaces as a repository that suddenly stops
building after a layer crosses the threshold rather than as a broken registry.
Reverting to 2.8 brings it back. Verify a fix with a layer big enough to go
multipart:

```bash
head -c 25000000 /dev/urandom > blob.bin
printf 'FROM scratch\nCOPY blob.bin /blob.bin\n' > Dockerfile
sudo docker build -t 127.0.0.1:30500/platform/pushtest:v1 . && \
  sudo docker push 127.0.0.1:30500/platform/pushtest:v1
```

## Prevention: enable S3/R2 (initial setup)

Use the setup script (bucket + vault keys):

```bash
# Dashboard keys in ~/.cf_r2_registry, then:
./bin/fleet-r2-registry --skip-bucket
make control-plane
```

Or manual vault + bucket:

1. Create R2 bucket (or use `./bin/fleet-r2-registry` without `--skip-bucket` and a bootstrap token with API Tokens Edit)
2. Add to vault:

```yaml
vault_registry_s3_access_key: "R2_ACCESS_KEY"
vault_registry_s3_secret_key: "R2_SECRET_KEY"
vault_registry_s3_bucket: "cronnecture-fleet-registry"
vault_registry_s3_region: "auto"
vault_registry_s3_endpoint: "https://ACCOUNT_ID.r2.cloudflarestorage.com"
```

3. Deploy:

```bash
make control-plane
```

4. Verify registry pod uses S3 (no PVC mount for data):

```bash
sudo k3s kubectl -n platform describe deploy fleet-registry
```

Existing PVC images are **not** auto-migrated — rebuild apps after switching (see below).

## Scenario A: Registry pod crash, PVC intact

```bash
sudo k3s kubectl -n platform rollout restart deployment/fleet-registry
sudo k3s kubectl -n platform rollout status deployment/fleet-registry
```

Test pull:

```bash
sudo k3s kubectl -n platform get svc fleet-registry
curl -si http://127.0.0.1:30500/v2/ | head -15   # 401 + Basic auth = NodePort up
```

## Scenario B: PVC lost, S3/R2 enabled

Images survive in bucket. Redeploy registry:

```bash
make control-plane
```

Re-trigger app builds from ops UI (or wait for pod restarts if image cached on compute nodes).

## Scenario C: PVC lost, no S3 (worst case)

1. All images gone from registry
2. **Running pods** may continue until restart
3. Rebuild every app:

```bash
# Per client in ops UI: Deploy → each app
# Or if ops UI down, manual Kaniko / docker build on compute
```

4. Enable S3/R2 immediately after recovery to prevent recurrence

## Scenario D: Disk full on control node

```bash
df -h /var/lib/rancher
sudo du -sh /var/lib/rancher/k3s/storage/* | sort -h | tail

# Registry PVC location (typical)
sudo du -sh /var/lib/rancher/k3s/storage/pvc-*

# Prune old images from registry (if delete enabled)
# Or expand disk / migrate to S3
```

Registry has `REGISTRY_STORAGE_DELETE_ENABLED=true` — GC unused tags via registry API or rebuild with S3 lifecycle rules.

## Scenario E: Restore PVC from backup tarball

If backup includes `registry/` tarball (optional weekly job):

```bash
# Stop registry
sudo k3s kubectl -n platform scale deployment/fleet-registry --replicas=0

# Restore to PVC path (path varies by k3s storage class)
# ... provider-specific ...

sudo k3s kubectl -n platform scale deployment/fleet-registry --replicas=1
```

Prefer S3 mode over PVC tarball restore for operational simplicity.

## Verification

```bash
curl -si http://127.0.0.1:30500/v2/ | head -15   # 401 expected without Basic auth
make health
# Trigger one test build from ops UI
```

## Related

- [resilience.md](../architecture/resilience.md)
- [RB-04 Deploy control plane](deploy-control-plane.md)
- [RB-07 Backup and restore](backup-restore.md)
