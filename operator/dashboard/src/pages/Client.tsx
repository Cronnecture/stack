import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Empty, PageHeader, Panel, Stat } from "../components/ui";
import { errDetail, openOperatorPortal, portalHref } from "../lib/format";

const TABS = ["Overview", "Portal", "Website", "Previews", "Billing"] as const;
type Tab = (typeof TABS)[number];

function tone(status?: string) {
  const s = (status || "").toLowerCase();
  if (["active", "live", "ready", "ok", "healthy", "bound"].includes(s)) return "ok" as const;
  if (["failed", "error", "deleting"].includes(s)) return "bad" as const;
  return "warn" as const;
}

export default function Client() {
  const { id } = useParams();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const { data: client, error, isLoading } = useQuery({
    queryKey: ["client", id],
    queryFn: async () => (await api.get(`/clients/${id}`)).data,
    refetchInterval: 8000,
    enabled: Boolean(id),
  });
  const templates = useQuery({
    queryKey: ["app-templates"],
    queryFn: async () => (await api.get("/app-templates")).data,
  });
  const packs = useQuery({
    queryKey: ["packs"],
    queryFn: async () => (await api.get("/clients/pack-catalog")).data,
  });
  const previews = useQuery({
    queryKey: ["previews", id],
    queryFn: async () => (await api.get("/previews", { params: { client_id: id } })).data,
    enabled: Boolean(id),
    refetchInterval: 10000,
  });
  const billing = useQuery({
    queryKey: ["billing", id],
    queryFn: async () => (await api.get(`/clients/${id}/billing`)).data,
    enabled: Boolean(id),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["client", id] });
    qc.invalidateQueries({ queryKey: ["previews", id] });
    qc.invalidateQueries({ queryKey: ["billing", id] });
    qc.invalidateQueries({ queryKey: ["jobs"] });
  };
  const act = useMutation({
    mutationFn: async (spec: { method?: string; path: string; body?: any }) => {
      const method = (spec.method || "post").toLowerCase();
      return (await api.request({ method, url: spec.path, data: spec.body })).data;
    },
    onSuccess: invalidate,
  });

  if (isLoading) return <p className="lead">Loading client…</p>;
  if (error) return <p className="bad">{errDetail(error)}</p>;
  if (!client) return <p className="bad">Client not found.</p>;

  const portal = client.portal || {};
  const apps = client.apps || [];
  const previewRows = previews.data?.previews || [];
  const protectedClient = client.slug === "noorddriveautos";
  const goLive = packs.data?.go_live || [{ id: "site_only", label: "Website" }];
  const tpls = Array.isArray(templates.data) ? templates.data : templates.data?.templates || [];

  return (
    <div>
      <PageHeader
        title={client.name}
        lead={`${client.slug} · ${client.k8s_namespace || "no namespace"}`}
        actions={
          <Link to="/clients">
            <button className="secondary" type="button">
              All clients
            </button>
          </Link>
        }
      />
      <div className="stats">
        <Stat value={client.status} label="Status" tone={tone(client.status)} />
        <Stat value={portal.status || "none"} label="Portal" tone={portal.url ? "ok" : "warn"} />
        <Stat value={apps.length} label="Apps" />
        <Stat value={client.logto_bound ? "Bound" : "Unbound"} label="Logto" tone={client.logto_bound ? "ok" : "warn"} />
      </div>
      <div className="tabs">
        {TABS.map((name) => (
          <button key={name} className={tab === name ? "tab active" : "tab"} type="button" onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </div>
      {act.isError && <p className="bad">{errDetail(act.error)}</p>}
      {act.isSuccess && <p className="ok">Queued. Job {act.data?.job_id || "accepted"}.</p>}

      {tab === "Overview" && (
        <div className="layout two">
          <Panel title="Account">
            <table>
              <tbody>
                <tr>
                  <td>Email</td>
                  <td>{client.contact_email || "—"}</td>
                </tr>
                <tr>
                  <td>Pack</td>
                  <td>{client.pack_label || client.pack || "—"}</td>
                </tr>
                <tr>
                  <td>Billing</td>
                  <td>{client.billing_status || "—"}</td>
                </tr>
                <tr>
                  <td>Logto</td>
                  <td>{client.logto_bound ? "bound" : "not bound"}</td>
                </tr>
                <tr>
                  <td>Status page</td>
                  <td>
                    {client.status_page_url ? (
                      <a className="ext" href={client.status_page_url} target="_blank" rel="noreferrer">
                        {client.status_page_url}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </Panel>
          <Panel title="Go live">
            {protectedClient ? (
              <p className="muted">Protected client. Provision actions are available for portal and apps, not teardown.</p>
            ) : null}
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                act.mutate({
                  path: `/clients/${id}/provision`,
                  body: {
                    pack: fd.get("pack"),
                    contact_email: client.contact_email,
                    access_emails: portal.access_emails || [client.contact_email].filter(Boolean),
                    bootstrap_site: fd.get("bootstrap_site") === "on",
                    zone_mode: "platform_subdomain",
                  },
                });
              }}
            >
              <label className="field">
                Pack
                <select name="pack" defaultValue={client.pack || "site_only"}>
                  {goLive.map((p: any) => (
                    <option key={p.id} value={p.id}>
                      {p.label || p.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="muted">
                <input name="bootstrap_site" type="checkbox" defaultChecked /> Bootstrap website app
              </label>
              <button type="submit" disabled={act.isPending}>
                Provision / go live
              </button>
            </form>
            <div className="actions">
              <button
                className="secondary"
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate({ path: `/clients/${id}/ensure-hosting`, body: { bootstrap_site: true } })}
              >
                Ensure hosting
              </button>
              <button
                className="secondary"
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate({ path: `/clients/${id}/portal/provision` })}
              >
                Provision portal
              </button>
            </div>
          </Panel>
        </div>
      )}

      {tab === "Portal" && (
        <div className="layout two">
          <Panel title="Customer portal">
            <p>
              {portalHref(client) ? (
                <button
                  className="secondary"
                  type="button"
                  onClick={() => openOperatorPortal(client.id).catch((err) => alert(errDetail(err)))}
                >
                  Open portal (Authentik)
                </button>
              ) : (
                <span className="muted">Not provisioned.</span>
              )}
            </p>
            <p className="muted">
              Status {portal.status || "none"} · host {portal.hostname || "—"}
              <br />
              Open portal uses your Authentik session on Control. Customers still sign in with Logto.
            </p>
            <div className="actions">
              <button
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate({ path: `/clients/${id}/portal/provision` })}
              >
                Provision portal
              </button>
            </div>
          </Panel>
          <Panel title="Logto allowlist">
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                const emails = String(fd.get("emails") || "")
                  .split(/[\s,]+/)
                  .map((x) => x.trim().toLowerCase())
                  .filter(Boolean);
                act.mutate({
                  method: "patch",
                  path: `/clients/${id}/portal`,
                  body: { access_emails: emails },
                });
              }}
            >
              <textarea
                name="emails"
                defaultValue={(portal.access_emails || portal.effective_access_emails || []).join("\n")}
                placeholder="one email per line"
              />
              <button type="submit" disabled={act.isPending}>
                Save invites
              </button>
            </form>
          </Panel>
        </div>
      )}

      {tab === "Website" && (
        <div className="layout two">
          <Panel title="Apps">
            <table>
              <thead>
                <tr>
                  <th>App</th>
                  <th>Status</th>
                  <th>Repo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {apps.map((a: any) => (
                  <tr key={a.id}>
                    <td>
                      {a.name}
                      <div className="muted">
                        {(a.exposures || []).map((e: any) => e.hostname).filter(Boolean).join(", ") || "no hostname"}
                      </div>
                    </td>
                    <td>
                      <Badge tone={tone(a.status)}>{a.status}</Badge>
                    </td>
                    <td>
                      <code>{a.github_repo || "—"}</code>
                    </td>
                    <td>
                      <button
                        className="secondary"
                        type="button"
                        disabled={act.isPending}
                        onClick={() =>
                          act.mutate({
                            path: `/clients/${id}/apps/${a.id}/deploy`,
                            body: { mode: "rebuild" },
                          })
                        }
                      >
                        Deploy
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {apps.length === 0 && <Empty>No apps yet. Bootstrap a site or attach a repo.</Empty>}
          </Panel>
          <Panel title="New website integration">
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                act.mutate({
                  path: `/clients/${id}/apps/new`,
                  body: {
                    name: fd.get("name"),
                    template: fd.get("template"),
                    expose_subdomain: fd.get("subdomain") || "www",
                    deploy: true,
                    attach_db: false,
                    private: true,
                  },
                });
              }}
            >
              <input name="name" placeholder="app name (site)" required defaultValue="site" />
              <label className="field">
                Template
                <select name="template" defaultValue="vite-react-ts">
                  {(tpls.length ? tpls : [{ id: "vite-react-ts", label: "Vite + React" }]).map((t: any) => (
                    <option key={t.id || t.name} value={t.id || t.name}>
                      {t.label || t.id || t.name}
                    </option>
                  ))}
                </select>
              </label>
              <input name="subdomain" placeholder="subdomain (www or @)" defaultValue="www" />
              <button type="submit" disabled={act.isPending}>
                Create and deploy
              </button>
            </form>
            <h2>From existing repo</h2>
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                act.mutate({
                  path: `/clients/${id}/apps/from-repo`,
                  body: {
                    name: fd.get("name"),
                    github_repo: fd.get("github_repo"),
                    github_branch: fd.get("branch") || "main",
                    deploy: true,
                  },
                });
              }}
            >
              <input name="name" placeholder="app name" required />
              <input name="github_repo" placeholder="owner/repo" required />
              <input name="branch" placeholder="branch" defaultValue="main" />
              <button className="secondary" type="submit" disabled={act.isPending}>
                Attach repo
              </button>
            </form>
          </Panel>
        </div>
      )}

      {tab === "Previews" && (
        <div className="layout two">
          <Panel title="Client previews">
            <table>
              <thead>
                <tr>
                  <th>Preview</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {previewRows.map((p: any) => (
                  <tr key={p.id}>
                    <td>
                      <a className="ext" href={p.url} target="_blank" rel="noreferrer">
                        {p.name}
                      </a>
                      <div className="muted">{p.path}</div>
                    </td>
                    <td>
                      <Badge tone={tone(p.status)}>{p.status}</Badge>
                    </td>
                    <td>
                      <div className="actions">
                        <button
                          className="secondary"
                          type="button"
                          disabled={act.isPending}
                          onClick={() => act.mutate({ path: `/previews/${p.id}/deploy`, body: { rebuild: true } })}
                        >
                          Deploy
                        </button>
                        <button
                          className="secondary"
                          type="button"
                          disabled={act.isPending}
                          onClick={() => act.mutate({ path: `/previews/${p.id}/promote-website`, body: { roll: true } })}
                        >
                          Promote
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {previewRows.length === 0 && <Empty>No previews for this client.</Empty>}
          </Panel>
          <Panel title="Ship preview">
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                act.mutate({
                  path: `/previews/ship`,
                  body: {
                    name: fd.get("name") || client.name,
                    source_url: fd.get("source_url") || undefined,
                    template: fd.get("template"),
                    client_id: Number(id),
                    deploy: true,
                  },
                });
              }}
            >
              <input name="name" placeholder="Preview name" defaultValue={client.name} />
              <input name="source_url" placeholder="Source URL (optional for blank-diy)" />
              <select name="template" defaultValue="vite-react-ts">
                <option value="vite-react-ts">Vite React</option>
                <option value="static-vite">Static Vite</option>
                <option value="blank-diy">Blank DIY</option>
                <option value="supabase-ready">Supabase ready</option>
              </select>
              <button type="submit" disabled={act.isPending}>
                Ship preview
              </button>
            </form>
          </Panel>
        </div>
      )}

      {tab === "Billing" && (
        <Panel title="Billing">
          <table>
            <tbody>
              <tr>
                <td>Status</td>
                <td>{client.billing_status || billing.data?.status || "—"}</td>
              </tr>
              <tr>
                <td>Plan</td>
                <td>{client.billing_plan || billing.data?.plan || "—"}</td>
              </tr>
              <tr>
                <td>Setup paid</td>
                <td>{client.setup_paid ? "yes" : "no"}</td>
              </tr>
            </tbody>
          </table>
          <div className="actions">
            <button
              className="secondary"
              type="button"
              disabled={act.isPending || !client.contact_email}
              onClick={() => act.mutate({ path: `/clients/${id}/billing/checkout` })}
            >
              Create checkout
            </button>
            <button
              className="secondary"
              type="button"
              disabled={act.isPending}
              onClick={() => act.mutate({ path: `/clients/${id}/billing/refresh` })}
            >
              Refresh
            </button>
          </div>
        </Panel>
      )}
    </div>
  );
}
