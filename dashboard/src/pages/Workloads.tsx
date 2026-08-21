import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default function Workloads() {
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
      <h1>Workloads</h1>
      <p className="lead">Pods on this cluster. Failed and pending are listed first.</p>
      <div className="grid four">
        <div className="card">
          <div className="stat">{data?.active_workloads ?? "–"}</div>
          <div className="label">Running</div>
        </div>
        <div className="card">
          <div className="stat">{data?.pending_workloads ?? "–"}</div>
          <div className="label">Pending</div>
        </div>
        <div className="card">
          <div className="stat">{data?.failed_workloads ?? "–"}</div>
          <div className="label">Failed</div>
        </div>
      </div>
      <div className="card" style={{ marginTop: "1rem" }}>
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
                <td className={w.status === "running" ? "ok" : "bad"}>{w.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
