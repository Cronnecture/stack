import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { cx } from "../lib/format";

const NAV = [
  {
    label: "Operate",
    items: [
      { to: "/", end: true, name: "Overview" },
      { to: "/clients", name: "Clients" },
      { to: "/previews", name: "Previews" },
      { to: "/jobs", name: "Jobs" },
    ],
  },
  {
    label: "Identity",
    items: [
      { to: "/identity", name: "Identity" },
      { to: "/mail", name: "Mail" },
    ],
  },
  {
    label: "Fleet",
    items: [
      { to: "/edge", name: "Edge" },
      { to: "/cluster", name: "Cluster" },
    ],
  },
];

export default function Shell() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/health")).data,
    refetchInterval: 15000,
  });

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">
          <span className="brand-mark">CN</span>
          <div>
            <div className="brand-name">Cronnecture</div>
            <div className="brand-sub">Control</div>
          </div>
        </div>
        {NAV.map((group) => (
          <div key={group.label} className="nav-group">
            <div className="nav-label">{group.label}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => cx("nav-link", isActive && "active")}
              >
                {item.name}
              </NavLink>
            ))}
          </div>
        ))}
        <div className="nav-foot">
          <span className={cx("pulse", health.data?.status === "healthy" && "ok")} />
          control.cronnecture.com
        </div>
      </aside>
      <div className="stage">
        <Outlet />
      </div>
    </div>
  );
}
