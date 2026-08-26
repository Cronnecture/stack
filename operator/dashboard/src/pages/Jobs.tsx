import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Empty, PageHeader, Panel, Stat } from "../components/ui";
import { fmtTime } from "../lib/format";

export default function Jobs() {
  const { data, error } = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => (await api.get("/jobs")).data,
    refetchInterval: 10000,
  });
  const jobs = data?.jobs || [];
  const failed = jobs.filter((j: any) => j.status === "failed").length;

  return (
    <div>
      <PageHeader title="Jobs" lead="Provision, teardown, and fleet jobs from the platform control-plane." />
      {error && <p className="bad">Could not load jobs.</p>}
      <div className="stats">
        <Stat value={data?.total ?? jobs.length} label="Listed" />
        <Stat value={failed} label="Failed in view" tone={failed ? "warn" : "ok"} />
      </div>
      <Panel title="Recent">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Status</th>
              <th>Created</th>
              <th>Log</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j: any) => (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td>
                  <code>{j.type}</code>
                </td>
                <td>
                  <Badge tone={j.status === "failed" ? "bad" : j.status === "completed" || j.status === "succeeded" ? "ok" : "warn"}>
                    {j.status}
                  </Badge>
                </td>
                <td className="muted">{fmtTime(j.created_at)}</td>
                <td>
                  <code>{(j.log_preview || "").slice(-120) || "—"}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {jobs.length === 0 && <Empty>No jobs.</Empty>}
      </Panel>
    </div>
  );
}
