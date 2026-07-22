interface SkeletonProps {
  className?: string;
}

/** A shimmering placeholder block used while content loads. */
export function Skeleton({ className }: SkeletonProps) {
  return <span className={`skeleton ${className ?? ""}`} aria-hidden="true" />;
}

/** Full loading placeholder that mirrors the dashboard layout. */
export function DashboardSkeleton() {
  return (
    <>
      <section className="kpi-section">
        <div className="kpi-grid">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="kpi-card tone-neutral">
              <Skeleton className="skeleton-line lg" />
              <Skeleton className="skeleton-line sm" />
            </div>
          ))}
        </div>
      </section>
      <nav className="tabs">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="skeleton-tab" />
        ))}
      </nav>
      <section className="tab-panel">
        <div className="skeleton-panel">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="skeleton-row" />
          ))}
        </div>
      </section>
    </>
  );
}
