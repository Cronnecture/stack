import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, PageHeader, Panel, Stat } from "../components/ui";

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
      <PageHeader
        title="Edge"
        lead="Cloudflare node-tunnel. HTTP origins are Traefik ClusterIP. Mail stays on a public A record."
      />
      <div className="stats">
        <Stat value={cf?.configured ? "On" : "Off"} label="API credentials" />
        <Stat value={cf?.http_on_traefik ? "Traefik" : "Check"} label="HTTP origin" tone={cf?.http_on_traefik ? "ok" : "warn"} />
        <Stat value={(cf?.tunnels || []).length} label="Tunnels" />
        <Stat
          value={exposure?.http_nodeports_closed ? "Closed" : "Open"}
          label="HTTP NodePorts"
          tone={exposure?.http_nodeports_closed ? "ok" : "warn"}
        />
      </div>
      <Panel title="Tunnel ingress">
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
                  {r.via_traefik ? <Badge tone="ok">traefik</Badge> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Traefik routes">
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
                <td>
                  <code>{(r.matches || []).join(" | ")}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
