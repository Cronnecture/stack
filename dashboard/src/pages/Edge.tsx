import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default function Edge() {
  const { data: cf } = useQuery({
    queryKey: ["cloudflare"],
    queryFn: async () => (await api.get("/cloudflare")).data,
    refetchInterval: 20000,
  });
  const { data: exposure } = useQuery({
    queryKey: ["exposure"],
    queryFn: async () => (await api.get("/exposure")).data,
    refetchInterval: 20000,
  });
  const { data: routes = [] } = useQuery({
    queryKey: ["routes"],
    queryFn: async () => (await api.get("/routes")).data,
    refetchInterval: 20000,
  });

  return (
    <div>
      <h1>Edge</h1>
      <p className="lead">
        Existing Cloudflare node-tunnel. HTTP origins are Traefik ClusterIP. Mail stays on a public A record.
      </p>
      <div className="grid four">
        <div className="card">
          <div className="stat">{cf?.configured ? "On" : "Off"}</div>
          <div className="label">API credentials</div>
        </div>
        <div className="card">
          <div className="stat">{cf?.http_on_traefik ? "Traefik" : "Check"}</div>
          <div className="label">HTTP origin</div>
        </div>
        <div className="card">
          <div className="stat">{(cf?.tunnels || []).length}</div>
          <div className="label">Tunnels</div>
        </div>
        <div className="card">
          <div className="stat">{exposure?.http_nodeports_closed ? "Closed" : "Open"}</div>
          <div className="label">HTTP NodePorts</div>
        </div>
      </div>

      <h2>Tunnel ingress</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Hostname</th>
              <th>Origin</th>
            </tr>
          </thead>
          <tbody>
            {(cf?.routes || []).map((r: any) => (
              <tr key={r.hostname}>
                <td>{r.hostname}</td>
                <td>
                  <code>{r.service}</code>
                  {r.via_traefik ? <span className="ok"> traefik</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Host ports</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Namespace</th>
              <th>Pod</th>
              <th>Port</th>
            </tr>
          </thead>
          <tbody>
            {(exposure?.host_ports || []).map((p: any) => (
              <tr key={`${p.pod}-${p.hostPort}`}>
                <td>{p.namespace}</td>
                <td>{p.pod}</td>
                <td>{p.hostPort}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(exposure?.nodeports || []).length > 0 && (
          <p className="label">
            Cluster NodePorts: {exposure.nodeports.map((n: any) => `${n.namespace}/${n.name}`).join(", ")}
          </p>
        )}
      </div>

      <h2>Traefik routes</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Namespace</th>
              <th>Name</th>
              <th>Match</th>
            </tr>
          </thead>
          <tbody>
            {routes.map((r: any) => (
              <tr key={`${r.namespace}/${r.name}`}>
                <td>{r.namespace}</td>
                <td>{r.name}</td>
                <td><code>{(r.matches || []).join(" | ")}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
