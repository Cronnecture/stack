import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default function Mail() {
  const qc = useQueryClient();
  const { data, error, isLoading } = useQuery({
    queryKey: ["mail"],
    queryFn: async () => (await api.get("/mail")).data,
    refetchInterval: 10000,
  });
  const restart = useMutation({
    mutationFn: async (name: string) => (await api.post(`/mail/restart/${name}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mail"] }),
  });

  if (isLoading) return <p className="lead">Loading mail…</p>;
  if (error) return <p className="bad">Could not load mail status.</p>;

  return (
    <div>
      <h1>Mail</h1>
      <p className="lead">
        Stalwart in namespace <code>mail</code>, owned by this stack. Data is PVC{" "}
        <code>stalwart-data</code>. Public ports {(data.public_ports || []).join(", ")}. Hostname{" "}
        {data.hostname}. Restart rolls the pod; it does not delete mailboxes.
      </p>
      <div className="grid four">
        <div className="card">
          <div className="stat">{data.healthy ? "Healthy" : "Check"}</div>
          <div className="label">Mail</div>
        </div>
        {(data.workloads || []).map((w: any) => (
          <div className="card" key={w.name}>
            <div className="stat">
              {w.ready}/{w.desired}
            </div>
            <div className="label">{w.name}</div>
            <button className="secondary" disabled={restart.isPending} onClick={() => restart.mutate(w.name)}>
              Restart
            </button>
          </div>
        ))}
      </div>
      {restart.isSuccess && <p className="ok">Restarting {restart.data.name}</p>}
      <h2>Storage</h2>
      <div className="card">
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
                <td className={p.phase === "Bound" ? "ok" : "bad"}>{p.phase}</td>
                <td>{p.storage}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Pods</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Pod</th>
              <th>Node</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(data.pods || []).map((p: any) => (
              <tr key={p.name}>
                <td>{p.name}</td>
                <td>{p.node}</td>
                <td className={p.status === "running" ? "ok" : "bad"}>{p.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
