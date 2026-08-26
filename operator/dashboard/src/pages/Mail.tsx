import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, PageHeader, Panel, Stat } from "../components/ui";

export default function Mail() {
  const qc = useQueryClient();
  const { data, error, isLoading } = useQuery({
    queryKey: ["mail"],
    queryFn: async () => (await api.get("/mail")).data,
    refetchInterval: 10000,
  });
  const inbox = useQuery({
    queryKey: ["inbox"],
    queryFn: async () => (await api.get("/inbox")).data,
    refetchInterval: 20000,
  });
  const mailboxes = useQuery({
    queryKey: ["mailboxes"],
    queryFn: async () => (await api.get("/mail/mailboxes")).data,
    refetchInterval: 30000,
  });
  const restart = useMutation({
    mutationFn: async (name: string) => (await api.post(`/mail/restart/${name}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mail"] }),
  });

  if (isLoading) return <p className="lead">Loading mail…</p>;
  if (error) return <p className="bad">Could not load mail status.</p>;

  const overview = inbox.data || {};
  const boxRows = Array.isArray(mailboxes.data)
    ? mailboxes.data
    : mailboxes.data?.mailboxes || [];

  return (
    <div>
      <PageHeader
        title="Mail"
        lead={`Stalwart in namespace mail. Public SMTP ${ (data.public_ports || []).join(", ") }. Restart rolls the pod; mailboxes stay on PVC.`}
      />
      <div className="stats">
        <Stat value={data.healthy ? "Healthy" : "Check"} label="Keep-set" tone={data.healthy ? "ok" : "bad"} />
        <Stat value={overview.configured ? "Configured" : "—"} label="Platform mail" />
        <Stat value={overview.storage || "—"} label="Storage" />
        <Stat value={overview.auth_ok ? "OK" : "Check"} label="Auth" tone={overview.auth_ok ? "ok" : "warn"} />
      </div>
      <div className="layout two">
        <Panel title="Workloads">
          <table>
            <thead>
              <tr>
                <th>Workload</th>
                <th>Ready</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(data.workloads || []).map((w: any) => (
                <tr key={w.name}>
                  <td>{w.name}</td>
                  <td>
                    <Badge tone={w.healthy ? "ok" : "bad"}>
                      {w.ready}/{w.desired}
                    </Badge>
                  </td>
                  <td>
                    <button className="secondary" disabled={restart.isPending} onClick={() => restart.mutate(w.name)}>
                      Restart
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ marginTop: "0.8rem" }}>
            Webmail:{" "}
            <a className="ext" href="https://webmail.cronnecture.com" target="_blank" rel="noreferrer">
              webmail.cronnecture.com
            </a>
          </p>
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
      <Panel title="Mailboxes">
        <table>
          <thead>
            <tr>
              <th>Address</th>
              <th>Domain</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {boxRows.map((m: any) => (
              <tr key={m.id || m.address}>
                <td>{m.address || m.email || m.name}</td>
                <td>{m.domain || "—"}</td>
                <td>{m.status || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
