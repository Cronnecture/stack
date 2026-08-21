import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

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
      <h1>Identity</h1>
      <p className="lead">
        Vaultwarden, Authentik, Logto, Passbolt, and Hanko in namespace <code>identity</code>.
        Passwords stay in Secret <code>{data.secret}</code> (not in git). PVCs are never deleted.
        Restart rolls a workload; it does not wipe data.
      </p>
      <div className="grid four">
        <div className="card">
          <div className="stat">{data.healthy ? "Healthy" : "Check"}</div>
          <div className="label">Identity</div>
        </div>
        <div className="card">
          <div className="stat">{data.secrets_present ? "Present" : "Missing"}</div>
          <div className="label">Secrets</div>
        </div>
      </div>

      <h2>Apps</h2>
      <div className="card">
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
                  <td className={w.healthy ? "ok" : "bad"}>
                    {w.ready ?? "–"}/{w.desired ?? "–"}
                  </td>
                  <td>
                    <button disabled={restart.isPending} onClick={() => restart.mutate(a.deploy)}>
                      Restart
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {restart.isSuccess && <p className="ok">Restarting {restart.data.name}</p>}
      </div>

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
    </div>
  );
}
