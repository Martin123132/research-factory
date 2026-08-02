import Link from "next/link";

export default function NotFound() {
  return (
    <section className="empty-state not-found">
      <span className="mono">404 / OUTSIDE HANGAR MAP</span>
      <h1>That station does not exist.</h1>
      <p>The catalogue contains WB-001 through WB-100.</p>
      <Link className="button button-primary" href="/workbenches">
        Return to the station floor
      </Link>
    </section>
  );
}
