/** Three shimmering ledger rows shown while a verify lookup runs (§7.3). */
export function SkeletonRows() {
  return (
    <div className="fade-in overflow-hidden rounded-card border border-line bg-white">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={`skeleton-row flex items-center gap-4 px-4 py-3.5 ${
            i > 0 ? 'border-t border-line' : ''
          }`}
          style={{ animationDelay: `${i * 120}ms` }}
        >
          <div className="h-3 w-28 rounded-full bg-line" />
          <div className="h-3 w-20 rounded-full bg-line" />
          <div className="h-3 flex-1 rounded-full bg-line" />
          <div className="h-3 w-14 rounded-full bg-line" />
        </div>
      ))}
    </div>
  );
}
