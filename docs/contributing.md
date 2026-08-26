# Contributing

## Before opening a PR

```bash
cd $FLEET_ROOT   # repo root; override if the checkout lives elsewhere
make check
make check-smoke
make ci          # vault-less: syntax-check + smoke + ansible-lint + gitleaks
```

There is no required pre-commit hook. `make ci` is the same gate GitHub Actions runs on every push and pull request (`.github/workflows/ci.yml`, job name `check + check-smoke`).

## Do not

- Commit `config/inventory/group_vars/all/vault.yml` or `config/.identity/`
- Expand ansible-runner **write** paths in `config/policies/fleet-operations.yml`
- Run `make site` unless an operator explicitly asked
- Force-push to `main`

## Control-plane image changes

1. `make control-plane-staging`
2. `curl -sf -H 'Host: staging-ops.cronnecture.com' http://127.0.0.1:30081/api/health/ready`
3. After merge: `make control-plane` (production)
4. Optional: `make cp-images` — fail if staging and production tags differ
