# Apps

Product checkouts used by the stack. Ansible vars:

| Dir | Var | What | Remote |
|---|---|---|---|
| `marketing/` | `stack_marketing_dir` | Public site (`cronnecture.com`) | https://github.com/Cronnecture/website |
| `portfolio/` | `stack_portfolio_dir` | Preview starter | https://github.com/Cronnecture/portfolio |
| `previews/` | `stack_previews_dir` | Live preview hub notes — sites ship via Ansible to `previews.cronnecture.com` | — |

From `/home/dev/stack`:

```bash
make marketing    # build apps/marketing, push NodePort 30500, roll cronnecture-website
make portfolio    # build apps/portfolio and push the same registry
```

Pushes to `main` on those remotes also auto-deploy: GitHub webhook → Kaniko. Website rolls `platform/cronnecture-website` (`cronnecture.com`). Portfolio rebuilds the registry image and any live preview that tracks that repo.

Local `k3s ctr import` is master-only. Workers pull `fleet-registry` — the script pushes `127.0.0.1:30500/platform/…`.
