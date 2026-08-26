import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Empty, PageHeader, Panel, Stat } from "../components/ui";
import { errDetail, openOperatorPortal, portalHref } from "../lib/format";

export default function Clients() {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState<any>(null);
  const [typed, setTyped] = useState("");
  const { data } = useQuery({
    queryKey: ["clients"],
    queryFn: async () => (await api.get("/clients")).data,
    refetchInterval: 15000,
  });
  const packs = useQuery({
    queryKey: ["packs"],
    queryFn: async () => (await api.get("/clients/pack-catalog")).data,
  });
  const clients = data?.clients || [];
  const create = useMutation({
    mutationFn: async (body: any) => (await api.post("/clients", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });
  const del = useMutation({
    mutationFn: async (row: any) =>
      (await api.delete(`/clients/${row.id}`, { params: { confirm: row.slug } })).data,
    onSuccess: () => {
      setConfirming(null);
      setTyped("");
      qc.invalidateQueries({ queryKey: ["clients"] });
    },
  });
  const goLive = packs.data?.go_live || [];

  return (
    <div>
      <PageHeader
        title="Clients"
        lead="Create, provision, and open a workspace. Portal, previews, and website integrations all run from the client page."
      />
      <div className="stats">
        <Stat value={clients.length} label="Clients" />
        <Stat value={clients.filter((c: any) => c.status === "active").length} label="Active" tone="ok" />
        <Stat value={clients.filter((c: any) => c.portal?.url).length} label="Portals" />
      </div>
      <div className="layout two">
        <Panel title="Portfolio">
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Status</th>
                <th>Pack</th>
                <th>Portal</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c: any) => {
                const protectedClient = c.slug === "noorddriveautos";
                return (
                  <tr key={c.id}>
                    <td>
                      <Link to={`/clients/${c.id}`}>{c.name}</Link>
                      <div className="muted">{c.slug}</div>
                    </td>
                    <td>
                      <Badge tone={c.status === "active" ? "ok" : "warn"}>{c.status}</Badge>
                    </td>
                    <td>{c.pack_label || c.pack || "—"}</td>
                    <td>
                      {portalHref(c) ? (
                        <button
                          className="secondary"
                          type="button"
                          onClick={() => openOperatorPortal(c.id).catch((err) => alert(errDetail(err)))}
                        >
                          Open portal
                        </button>
                      ) : (
                        <span className="muted">none</span>
                      )}
                    </td>
                    <td>
                      {protectedClient ? (
                        <span className="muted">protected</span>
                      ) : confirming?.id === c.id ? (
                        <form
                          className="stack"
                          onSubmit={(e) => {
                            e.preventDefault();
                            if (typed === c.slug) del.mutate(c);
                          }}
                        >
                          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={`type ${c.slug}`} />
                          <button className="danger" disabled={typed !== c.slug || del.isPending} type="submit">
                            Confirm delete
                          </button>
                          <button className="secondary" type="button" onClick={() => setConfirming(null)}>
                            Cancel
                          </button>
                        </form>
                      ) : (
                        <div className="actions">
                          <Link to={`/clients/${c.id}`}>
                            <button className="secondary" type="button">
                              Open
                            </button>
                          </Link>
                          <button className="danger" type="button" onClick={() => setConfirming(c)}>
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {clients.length === 0 && <Empty>No clients in the portfolio.</Empty>}
          {del.isError && <p className="bad">{errDetail(del.error)}</p>}
          {del.isSuccess && <p className="ok">Teardown queued.</p>}
        </Panel>
        <Panel title="Create client">
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const email = String(fd.get("email") || "");
              create.mutate({
                slug: fd.get("slug"),
                name: fd.get("name"),
                contact_email: email,
                access_emails: [email],
                pack: fd.get("pack") || "site_only",
                provision: fd.get("provision") === "on",
              });
            }}
          >
            <input name="name" placeholder="Display name" required />
            <input name="slug" placeholder="slug" required />
            <input name="email" type="email" placeholder="Account email (Authentik + billing)" required />
            <label className="field">
              Pack
              <select name="pack" defaultValue="site_only">
                {(goLive.length ? goLive : [{ id: "site_only", label: "Website" }]).map((p: any) => (
                  <option key={p.id} value={p.id}>
                    {p.label || p.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="muted">
              <input name="provision" type="checkbox" /> Provision namespace, portal, and pack now
            </label>
            <button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create"}
            </button>
            {create.isSuccess && (
              <p className="ok">
                Created{" "}
                <Link to={`/clients/${create.data.id}`}>{create.data.slug || create.data.name}</Link>
                {create.data.job_id ? ` · job ${create.data.job_id}` : ""}
              </p>
            )}
            {create.isError && <p className="bad">{errDetail(create.error)}</p>}
          </form>
        </Panel>
      </div>
    </div>
  );
}
