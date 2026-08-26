import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, PageHeader, Panel, Stat } from "../components/ui";

export default function Overview() {
  const { data, error, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ["overview"],
    queryFn: async () => (await api.get("/overview")).data,
    refetchInterval: 15000,
  });

  if (isLoading) return <p className="lead">Loading control plane…</p>;
  if (error) return <p className="bad">Control plane API is unreachable.</p>;

  const keep = data.keep_set || {};
  const probes = data.probes || [];
  const keepOk = Object.values(keep).every((info: any) => info?.healthy);
  const probesOk = probes.every((p: any) => p.healthy);
  const metrics = data.portfolio?.metrics || {};
  const clients = data.clients || [];
  const overall = keepOk && probesOk ? "Operational" : "Degraded";

  return (
    <div>
      <PageHeader
        title="Overview"
        lead={`Single operator plane at control.cronnecture.com. Updated ${new Date(dataUpdatedAt).toLocaleTimeString()}.`}
      />
      <div className="stats">
        <Stat value={overall} label="Control plane" tone={keepOk && probesOk ? "ok" : "warn"} />
        <Stat value={`${(data.nodes || []).filter((n: any) => n.status === "ready").length}/${(data.nodes || []).length}`} label="Nodes ready" />
        <Stat value={clients.length} label="Clients" />
        <Stat value={metrics.failed_jobs_open ?? "—"} label="Failed jobs" tone={metrics.failed_jobs_open ? "warn" : "ok"} />
      </div>
      <div className="layout two">
        <Panel title="Endpoints">
          <table>
            <thead>
              <tr>
                <th>Service</th>
                <th>Status</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {probes.map((p: any) => (
                <tr key={p.name}>
                  <td>
                    <span className={`dot ${p.healthy ? "ok" : "bad"}`} />
                    {p.name}
                  </td>
                  <td>
                    <Badge tone={p.healthy ? "ok" : "bad"}>{p.status || p.error || "fail"}</Badge>
                  </td>
                  <td>
                    {p.kind === "https" ? (
                      <a className="ext" href={p.url.replace(/\/alive$/, "")} target="_blank" rel="noreferrer">
                        {p.url.replace(/^https:\/\//, "").replace(/\/alive$/, "")}
                      </a>
                    ) : (
                      <code>{p.url}</code>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Keep-set">
          <table>
            <thead>
              <tr>
                <th>Namespace</th>
                <th>Pods</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(keep).map(([name, info]: [string, any]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>
                    {info.running ?? "–"}/{info.pods ?? "–"}
                  </td>
                  <td>
                    <Badge tone={info.healthy ? "ok" : "bad"}>{info.healthy ? "healthy" : "check"}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
      {(data.failed_workloads || []).length > 0 && (
        <Panel title="Failed workloads">
          {(data.failed_workloads || []).map((w: any) => (
            <div key={`${w.namespace}/${w.name}`} className="bad">
              {w.namespace}/{w.name} ({w.status})
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}
