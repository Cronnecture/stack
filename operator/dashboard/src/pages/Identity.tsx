import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, PageHeader, Panel, Stat } from "../components/ui";

export default function Identity() {
  const qc = useQueryClient();
  const { data, error, isLoading } = useQuery({
    queryKey: ["identity"],
    queryFn: async () => (await api.get("/identity")).data,
    refetchInterval: 10000,
  });
  const restart = useMutation({
    mutationFn: async (name: string) => (await api.post(`/identity/restart/${name}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["identity"] }),
  });

  if (isLoading) return <p className="lead">Loading identity…</p>;
  if (error) return <p className="bad">Could not load identity status.</p>;

  return (
    <div>
      <PageHeader
        title="Identity"
        lead="Authentik, Vaultwarden, Passbolt, and Cerbos. Product and ops SSO is Authentik."
      />
      <div className="stats">
        <Stat value={data.healthy ? "Healthy" : "Check"} label="Identity" tone={data.healthy ? "ok" : "bad"} />
        <Stat value={data.secrets_present ? "Present" : "Missing"} label="Secrets" tone={data.secrets_present ? "ok" : "bad"} />
        <Stat value={data.authentik?.healthy ? "Live" : "Check"} label="Authentik" tone={data.authentik?.healthy ? "ok" : "warn"} />
      </div>
      <Panel title="Workloads">
        <table>
          <thead>
            <tr>
              <th>App</th>
              <th>Workload</th>
              <th>Ready</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data.apps || []).map((a: any) => {
              const w = (data.workloads || []).find((x: any) => x.name === a.deploy) || {};
              return (
                <tr key={a.deploy}>
                  <td>
                    {a.url ? (
                      <a className="ext" href={a.url} target="_blank" rel="noreferrer">
                        {a.name}
                      </a>
                    ) : (
                      a.name
                    )}
                  </td>
                  <td>{a.deploy}</td>
                  <td>
                    <Badge tone={w.healthy ? "ok" : "bad"}>
                      {w.ready ?? "–"}/{w.desired ?? "–"}
                    </Badge>
                  </td>
                  <td>
                    <button className="secondary" disabled={restart.isPending} onClick={() => restart.mutate(a.deploy)}>
                      Restart
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
      <div className="layout two">
        <Panel title="Authentik">
          <table>
            <tbody>
              <tr>
                <td>Role</td>
                <td>Ops (Cloudflare Access) and customer portal OIDC</td>
              </tr>
              <tr>
                <td>Issuer</td>
                <td>
                  <code>https://auth.cronnecture.com/application/o/cronnecture-client-portal/</code>
                </td>
              </tr>
              <tr>
                <td>Login</td>
                <td>
                  <code>/api/auth/oidc/login</code>
                </td>
              </tr>
            </tbody>
          </table>
        </Panel>
        <Panel title="Storage">
          <table>
            <thead>
              <tr>
                <th>PVC</th>
                <th>Phase</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {(data.pvcs || []).map((p: any) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>
                    <Badge tone={p.phase === "Bound" ? "ok" : "bad"}>{p.phase}</Badge>
                  </td>
                  <td>{p.storage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
