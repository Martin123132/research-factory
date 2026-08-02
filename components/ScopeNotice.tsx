export function ScopeNotice({ compact = false }: { compact?: boolean }) {
  return (
    <aside className={compact ? "scope-notice compact" : "scope-notice"}>
      <span className="scope-notice-icon">!</span>
      <div>
        <strong>Synthetic commissioning — not scientific evidence</strong>
        {!compact && (
          <p>
            Work-order completion here proves only that a piece of factory plumbing was exercised.
            It contributes zero independent reproductions and is never eligible for promotion.
          </p>
        )}
      </div>
    </aside>
  );
}
