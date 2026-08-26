import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Empty, PageHeader, Panel, Stat } from "../components/ui";
import { errDetail } from "../lib/format";

function tone(status?: string) {
  const s = (status || "").toLowerCase();
  if (["live", "ready", "active"].includes(s)) return "ok" as const;
  if (["failed", "error", "taken_down"].includes(s)) return "bad" as const;
  return "warn" as const;
}

export default function Previews() {
  const qc = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ["previews"],
    queryFn: async () => (await api.get("/previews")).data,
    refetchInterval: 10000,
  });
  const clients = useQuery({
    queryKey: ["clients"],
    queryFn: async () => (await api.get("/clients")).data,
  });
  const rows = data?.previews || [];
  const act = useMutation({
    mutationFn: async (spec: { method?: string; path: string; body?: any }) => {
      const method = (spec.method || "post").toLowerCase();
      return (await api.request({ method, url: spec.path, data: spec.body })).data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["previews"] }),
  });
  const live = rows.filter((p: any) => ["live", "ready", "active"].includes((p.status || "").toLowerCase())).length;

  return (
    <div>
      <PageHeader
        title="Previews"
        lead="Ship a demo on previews.cronnecture.com, deploy, then promote to a website when it is ready."
      />
      {error && <p className="bad">{errDetail(error)}</p>}
      <div className="stats">
        <Stat value={rows.length} label="Previews" />
        <Stat value={live} label="Live" tone="ok" />
      </div>
      <div className="layout two">
        <Panel title="Fleet">
          <table>
            <thead>
              <tr>
                <th>Preview</th>
                <th>Client</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p: any) => (
                <tr key={p.id}>
                  <td>
                    <a className="ext" href={p.url} target="_blank" rel="noreferrer">
                      {p.name}
                    </a>
                    <div className="muted">{p.path}</div>
                  </td>
                  <td>
                    {p.client_id ? (
                      <Link to={`/clients/${p.client_id}`}>{p.client_id}</Link>
                    ) : (
                      "—"
                    )}
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
                        Promote to website
                      </button>
                      <button
                        className="danger"
                        type="button"
                        disabled={act.isPending}
                        onClick={() => act.mutate({ method: "delete", path: `/previews/${p.id}` })}
                      >
                        Purge
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <Empty>No previews.</Empty>}
          {act.isError && <p className="bad">{errDetail(act.error)}</p>}
          {act.isSuccess && <p className="ok">Queued. Job {act.data?.job_id || "accepted"}.</p>}
        </Panel>
        <Panel title="Ship a preview">
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const clientId = fd.get("client_id");
              act.mutate({
                path: "/previews/ship",
                body: {
                  name: fd.get("name"),
                  source_url: fd.get("source_url") || undefined,
                  template: fd.get("template"),
                  client_id: clientId ? Number(clientId) : undefined,
                  deploy: true,
                },
              });
            }}
          >
            <input name="name" placeholder="Name" required />
            <input name="source_url" placeholder="Source URL (optional for blank-diy)" />
            <select name="template" defaultValue="vite-react-ts">
              <option value="vite-react-ts">Vite React</option>
              <option value="static-vite">Static Vite</option>
              <option value="blank-diy">Blank DIY</option>
              <option value="supabase-ready">Supabase ready</option>
            </select>
            <select name="client_id" defaultValue="">
              <option value="">No client (demo only)</option>
              {(clients.data?.clients || []).map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button type="submit" disabled={act.isPending}>
              {act.isPending ? "Shipping…" : "Ship"}
            </button>
          </form>
        </Panel>
      </div>
    </div>
  );
}
