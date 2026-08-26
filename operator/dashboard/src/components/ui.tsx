import { ReactNode } from "react";
import { cx } from "../lib/format";

export function PageHeader({
  title,
  lead,
  actions,
}: {
  title: string;
  lead?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {lead ? <p className="lead">{lead}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function Stat({ value, label, tone }: { value: ReactNode; label: string; tone?: "ok" | "bad" | "warn" }) {
  return (
    <div className="stat-card">
      <div className={cx("stat", tone)}>{value}</div>
      <div className="muted">{label}</div>
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "ok" | "bad" | "warn" | "neutral" }) {
  return <span className={cx("badge", tone)}>{children}</span>;
}

export function Panel({ title, children, wide }: { title?: string; children: ReactNode; wide?: boolean }) {
  return (
    <section className={cx("panel", wide && "wide")}>
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted empty">{children}</p>;
}
