import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

type SummaryRow = { active: string; resolved: string; newest: Date | null };
type UnresolvedRow = { letterboxd_slug: string; title_raw: string; first_seen: Date };

export default async function WatchlistPage() {
  const [summaryRows, unresolved] = await Promise.all([
    query<SummaryRow>(`
      select count(*) filter (where removed_at is null) as active,
             count(*) filter (where removed_at is null and tmdb_id is not null) as resolved,
             max(first_seen) as newest
      from watchlist_entry
    `),
    query<UnresolvedRow>(`
      select w.letterboxd_slug, w.title_raw, w.first_seen
      from watchlist_entry w
      where w.removed_at is null and w.tmdb_id is null
      order by w.first_seen desc
    `),
  ]);

  const summary = summaryRows[0];
  const active = Number(summary.active);
  const resolved = Number(summary.resolved);

  return (
    <main>
      <div className="flex flex-wrap items-baseline justify-between gap-4 pt-6 pb-8">
        <div className="grid grid-cols-2 gap-6">
          <Stat value={active} label="On the watchlist" />
          <Stat value={resolved} label="Resolved" />
        </div>
        {summary.newest && (
          <div className="text-[12px] tracking-[.14em] text-sage uppercase">
            Newest {formatDate(summary.newest)}
          </div>
        )}
      </div>

      <div className="sprocket thin" />

      <h2 className="mt-11 mb-2 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        Unresolved
      </h2>
      <p className="mb-4 text-sage">Usually television, sortie only tracks cinema showtimes.</p>

      {unresolved.length === 0 ? (
        <p className="border-t border-line py-5 text-sage">Every film resolved.</p>
      ) : (
        <div>
          {unresolved.map((w) => (
            <div
              key={w.letterboxd_slug}
              className="flex items-baseline justify-between gap-4 border-t border-line py-3 hover:bg-green-2"
            >
              <span className="min-w-0 font-display font-semibold">{w.title_raw}</span>
              <span className="num shrink-0 text-[13px] text-sage">{formatDate(w.first_seen)}</span>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <div className="num font-display text-[clamp(40px,7vw,68px)] leading-[0.9] font-extrabold tracking-tight">
        {value.toLocaleString()}
      </div>
      <div className="mt-2 text-[12px] tracking-[.14em] text-sage uppercase">{label}</div>
    </div>
  );
}

function formatDate(d: Date) {
  return new Date(d).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
}
