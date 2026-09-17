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
      <div className="grid grid-cols-1 gap-6 pt-6 pb-8">
        <Stat value={rows.length} label="Need a decision" accent />
      </div>

      <div className="sprocket thin" />

      <h2 className="mt-11 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        Matches
      </h2>

      {rows.length === 0 ? (
        <p className="border-t border-line py-5 text-sage">Every listing matched.</p>
      ) : (
        <div>
          {rows.map((row) => (
            <div key={row.id} className="border-t border-line py-[22px]">
              <div className="font-display text-[clamp(22px,3.2vw,30px)] leading-[1.05] font-bold tracking-tight">
                {row.raw_title}
              </div>
              <div className="mt-1.5 text-[13px] text-sage">{listingFacts(row)}</div>
              {row.film_url && (
                <a
                  href={row.film_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-[13px] text-sage underline hover:text-orange"
                >
                  View listing
                </a>
              )}
              <CandidateForm queueId={row.id} candidates={row.candidates} />
            </div>
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

function Stat({ value, label, accent }: { value: number; label: string; accent?: boolean }) {
  return (
    <div>
      <div
        className={`num font-display text-[clamp(40px,7vw,68px)] leading-[0.9] font-extrabold tracking-tight ${
          accent ? "text-orange" : ""
        }`}
      >
        {value.toLocaleString()}
      </div>
      <div className="mt-2 text-[12px] tracking-[.14em] text-sage uppercase">{label}</div>
    </div>
  );
}
