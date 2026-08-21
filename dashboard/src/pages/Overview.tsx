import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default function Overview() {
  const { data, error, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ["overview"],
    queryFn: async () => (await api.get("/overview")).data,
    refetchInterval: 15000,
  });

  if (isLoading) return <p className="lead">Loading cluster…</p>;
  if (error) return <p className="bad">Control plane API is unreachable.</p>;

  const keep = data.keep_set || {};
  const probes = data.probes || [];
  const keepOk = Object.values(keep).every((info: any) => info?.healthy);
  const probesOk = probes.every((p: any) => p.healthy);
  const exposure = data.exposure || {};
  const cf = data.cloudflare || {};

  return (
    <div>
      <h1>Overview</h1>
      <p className="lead">
        Live keep-set. HTTP through Cloudflare tunnels. Mail SMTP is the only public origin.
        Updated {new Date(dataUpdatedAt).toLocaleTimeString()}.
      </p>
      <div className="grid four">
        <div className="card">
          <div className="stat">{keepOk && probesOk ? "Healthy" : "Degraded"}</div>
          <div className="label">System</div>
        </div>
        <div className="card">
          <div className="stat">{(data.nodes || []).filter((n: any) => n.status === "ready").length}/{(data.nodes || []).length}</div>
          <div className="label">Nodes ready</div>
        </div>
        <div className="card">
          <div className="stat">{cf.http_on_traefik ? "Tunnel" : "Check"}</div>
          <div className="label">HTTP origin</div>
        </div>
        <div className="card">
          <div className="stat">{(data.clients || []).length}</div>
          <div className="label">Clients</div>
        </div>
      </div>

      <h2>Endpoints</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Namespace</th>
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
                <td>{p.ns}</td>
                <td className={p.healthy ? "ok" : "bad"}>{p.status || p.error || "fail"}</td>
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
      </div>

      <h2>Keep-set</h2>
      <div className="grid four">
        {Object.entries(keep).map(([name, info]: [string, any]) => (
          <div className="card" key={name}>
            <div className="stat">
              {info.running ?? "–"}/{info.pods ?? "–"}
            </div>
            <div className="label">{name}</div>
            <div className={info.healthy ? "ok" : "bad"}>{info.healthy ? "healthy" : "check"}</div>
          </div>
        ))}
      </div>

      <h2>Nodes</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>IP</th>
              <th>Role</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(data.nodes || []).map((n: any) => (
              <tr key={n.name}>
                <td>{n.name}</td>
                <td><code>{n.ip}</code></td>
                <td>{n.role}</td>
                <td className={n.status === "ready" ? "ok" : "bad"}>{n.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(data.failed_workloads || []).length > 0 && (
        <>
          <h2>Failed pods</h2>
          <div className="card">
            {(data.failed_workloads || []).map((w: any) => (
              <div key={`${w.namespace}/${w.name}`} className="bad">
                {w.namespace}/{w.name} ({w.status})
              </div>
            ))}
          </div>
        </>
      )}

      <p className="label" style={{ marginTop: "1rem" }}>
        WAN: UFW deny except 25/587. Remaining NodePort: fleet-registry 30500 (cluster only).
        HTTP NodePorts closed: {exposure.http_nodeports_closed ? "yes" : "no"}.
      </p>
    </div>
  );
}
