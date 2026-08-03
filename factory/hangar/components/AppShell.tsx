import Link from "next/link";
import { getChatGPTUser } from "@/app/chatgpt-auth";

export async function AppShell({ children }: { children: React.ReactNode }) {
  const user = await getChatGPTUser();

  return (
    <div className="site-shell">
      <div className="scope-strip">
        <span>Synthetic commissioning — not scientific evidence</span>
        <span>Live research lane locked</span>
      </div>
      <header className="site-header">
        <Link className="brand" href="/" aria-label="Research Factory Hangar home">
          <span className="brand-mark"><i /><i /><i /></span>
          <span><strong>Research Factory</strong><small>Hangar 01</small></span>
        </Link>
        <nav aria-label="Primary navigation">
          <Link href="/workbenches">Stations</Link>
          <Link href="/operations">Shift board</Link>
          <Link href="/runners">Runners</Link>
          <Link href="/history">History</Link>
          <Link href="/architecture">System</Link>
          <Link href="/standards">Standards</Link>
          <Link href="/tutorial">Tutorial</Link>
          <Link href="/contribute">Contribute</Link>
        </nav>
        <div className="operator-chip">
          <span className={user ? "operator-light online" : "operator-light"} />
          <span><small>Operator</small><strong>{user?.displayName ?? "Local preview"}</strong></span>
        </div>
      </header>
      <main className="site-main">{children}</main>
      <footer className="site-footer">
        <div><strong>Research Factory / Hangar 01</strong><span>Construction and commissioning workspace</span></div>
        <div className="footer-boundary"><span>Scientific evidence</span><strong>OFFLINE BY DESIGN</strong></div>
      </footer>
    </div>
  );
}
