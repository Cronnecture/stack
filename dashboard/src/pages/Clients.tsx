import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default function Clients() {
  const qc = useQueryClient();
  const { data: clients = [] } = useQuery({
    queryKey: ["clients"],
    queryFn: async () => (await api.get("/clients")).data,
    refetchInterval: 15000,
  });
  const mutation = useMutation({
    mutationFn: async (body: any) => (await api.post("/onboard", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });

  return (
    <div>
      <h1>Clients</h1>
      <p className="lead">
        Live client-* namespaces. Provisioning creates a namespace, nginx placeholder, and Traefik
        route. It does not touch mail or identity.
      </p>
      <div className="grid two">
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Running</h2>
          <table>
            <thead>
              <tr>
                <th>Namespace</th>
                <th>Tier</th>
                <th>Pods</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c: any) => (
                <tr key={c.namespace}>
                  <td>{c.namespace}</td>
                  <td>{c.tier}</td>
                  <td>
                    {c.pods_running}/{c.pods_total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {clients.length === 0 && <p className="label">No client namespaces.</p>}
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Provision</h2>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              mutation.mutate({
                client_name: fd.get("client_name"),
                email: fd.get("email"),
                phone: fd.get("phone") || "",
                domain: fd.get("domain"),
                service_tier: fd.get("service_tier") || "website",
                template: fd.get("template") || "business",
              });
            }}
          >
            <input name="client_name" placeholder="Client name" required />
            <input name="domain" placeholder="example.com" required />
            <input name="email" type="email" placeholder="contact email" required />
            <select name="service_tier" defaultValue="website">
              <option value="website">website</option>
              <option value="webshop">webshop</option>
              <option value="portal">portal</option>
            </select>
            <button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Provisioning…" : "Create namespace"}
            </button>
            {mutation.isSuccess && (
              <p className="ok">{mutation.data.status}: {mutation.data.access_url || mutation.data.workflow_id}</p>
            )}
            {mutation.isError && <p className="bad">Provision failed.</p>}
          </form>
        </div>
      </div>
    </div>
  );
}
