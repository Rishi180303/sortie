import { query } from "@/lib/db";
import { CandidateForm } from "./candidate-form";

export const dynamic = "force-dynamic";

type Candidate = {
  tmdb_id: number;
  title: string;
  year: number | null;
  director: string | null;
  runtime_minutes: number | null;
  score: number;
};

type QueueRow = {
  id: number;
  candidates: Candidate[];
  created_at: Date;
  source_film_id: number;
  raw_title: string;
  raw_year: number | null;
  director: string | null;
  runtime_minutes: number | null;
  source: string;
  film_url: string | null;
};

export default async function MatchesPage() {
  const rows = await query<QueueRow>(`
    select q.id, q.candidates, q.created_at,
           sf.id as source_film_id, sf.raw_title, sf.raw_year, sf.director,
           sf.runtime_minutes, sf.source, sf.film_url
    from match_queue q
    join source_film sf on sf.id = q.source_film_id
    where q.resolved_at is null
    order by q.created_at desc
  `);

  return (
    <main>
      <h2 className="pt-6 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        Matches <span className="num text-sage">{rows.length}</span>
      </h2>

      {rows.length === 0 ? (
        <p className="border-t border-line py-5 text-sage">Every listing matched.</p>
      ) : (
        <div>
          {rows.map((row) => (
            <details key={row.id} className="group border-t border-line">
              <summary className="flex list-none cursor-pointer items-baseline justify-between gap-4 py-[22px] hover:bg-green-2 [&::-webkit-details-marker]:hidden">
                <span className="flex items-baseline gap-2 font-display text-[17px] font-bold tracking-tight">
                  <span className="text-sage">
                    <span className="group-open:hidden">▸</span>
                    <span className="hidden group-open:inline">▾</span>
                  </span>
                  {row.raw_title}
                </span>
                <span className="shrink-0 text-[13px] text-sage">{listingFacts(row)}</span>
              </summary>
              <div className="pb-[22px] pl-6">
                {row.film_url && (
                  // ponytail: fandango is the only source today so film_url is always a fandango
                  // path; a second source will need to carry its own host alongside the path
                  <a
                    href={new URL(row.film_url, "https://www.fandango.com").href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-[13px] text-sage underline hover:text-orange"
                  >
                    View listing
                  </a>
                )}
                <CandidateForm queueId={row.id} candidates={row.candidates} />
              </div>
            </details>
          ))}
        </div>
      )}
    </main>
  );
}

function listingFacts(row: QueueRow) {
  return [
    row.source,
    row.director,
    row.runtime_minutes ? `${row.runtime_minutes} min` : null,
    row.raw_year ? `listed as ${row.raw_year}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
