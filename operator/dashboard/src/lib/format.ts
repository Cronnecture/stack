import { api } from "./api";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function errDetail(e: any) {
  const d = e?.response?.data?.detail;
  if (Array.isArray(d)) return d.map((x: any) => x.msg || x.detail || JSON.stringify(x)).join("; ");
  if (typeof d === "object" && d) return d.message || JSON.stringify(d);
  return d || e?.message || "Request failed";
}

export function portalHref(client: any) {
  const raw = (client?.portal_url || client?.portal?.url || "").trim();
  if (!raw) return "";
  return raw.endsWith("/") ? raw : `${raw}/`;
}

export async function openOperatorPortal(clientId: number | string) {
  const tab = window.open("about:blank", "_blank");
  try {
    const { data } = await api.post(`/clients/${clientId}/portal/ops-access`);
    if (!data?.url) throw new Error("Portal link was not issued");
    if (tab) {
      tab.opener = null;
      tab.location.replace(data.url);
    } else {
      window.location.assign(data.url);
    }
  } catch (err) {
    if (tab) tab.close();
    throw err;
  }
}

export function fmtTime(value?: string | number | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}
