import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, PageHeader, Panel, Stat } from "../components/ui";

export default function Cluster() {
  const { data: overview } = useQuery({
    queryKey: ["overview"],
    queryFn: async () => (await api.get("/overview")).data,
    refetchInterval: 15000,
  });
  const { data } = useQuery({
    queryKey: ["workloads"],
    queryFn: async () => (await api.get("/workloads")).data,
    refetchInterval: 15000,
  });
  const rows = [...(data?.workloads || [])].sort((a: any, b: any) => {
    const rank = (s: string) => (s === "running" ? 2 : s === "pending" ? 1 : 0);
    return rank(a.status) - rank(b.status);
  });

  return (
    <div>
      <PageHeader title="Cluster" lead="Nodes and pods on this k3s cluster. Failed and pending are listed first." />
      <div className="stats">
        <Stat
          value={`${(overview?.nodes || []).filter((n: any) => n.status === "ready").length}/${(overview?.nodes || []).length}`}
          label="Nodes ready"
        />
        <Stat value={data?.active_workloads ?? "–"} label="Running" />
        <Stat value={data?.pending_workloads ?? "–"} label="Pending" />
        <Stat value={data?.failed_workloads ?? "–"} label="Failed" tone={data?.failed_workloads ? "bad" : "ok"} />
      </div>
      <Panel title="Nodes">
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
            {(overview?.nodes || []).map((n: any) => (
              <tr key={n.name}>
                <td>{n.name}</td>
                <td>
                  <code>{n.ip}</code>
                </td>
                <td>{n.role}</td>
                <td>
                  <Badge tone={n.status === "ready" ? "ok" : "bad"}>{n.status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Workloads">
        <table>
          <thead>
            <tr>
              <th>Pod</th>
              <th>Namespace</th>
              <th>Node</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((w: any) => (
              <tr key={`${w.namespace}/${w.name}`}>
                <td>{w.name}</td>
                <td>{w.namespace}</td>
                <td>{w.node}</td>
                <td>
                  <Badge tone={w.status === "running" ? "ok" : "bad"}>{w.status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
