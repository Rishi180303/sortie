"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Candidate = {
  tmdb_id: number;
  title: string;
  year: number | null;
  director: string | null;
  runtime_minutes: number | null;
  score: number;
};

export function CandidateForm({ queueId, candidates }: { queueId: number; candidates: Candidate[] }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resolve(tmdbId: number | null) {
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queueId, tmdbId }),
      });
      if (!res.ok) {
        setError("Save failed. Try again.");
        setPending(false);
        return;
      }
      router.refresh();
    } catch {
      setError("Save failed. Try again.");
      setPending(false);
    }
  }

  const sorted = [...candidates].sort((a, b) => b.score - a.score);

  return (
    <div>
      <div className="mt-3.5">
        {sorted.length === 0 && <p className="text-[13px] text-sage">No candidates found.</p>}
        {sorted.map((c, i) => (
          <div
            key={c.tmdb_id}
            className="-mx-3 grid grid-cols-[64px_1fr_auto] items-center gap-4 px-3 py-2.5 max-sm:grid-cols-[52px_1fr] max-sm:gap-y-1.5 hover:bg-green-2"
          >
            <span
              className={`num font-display text-[22px] font-extrabold ${i === 0 ? "text-orange" : "text-sage"}`}
            >
              {formatScore(c.score)}
            </span>
            <span>
              <span className="font-semibold">{c.title}</span>
              <br />
              <span className="text-[13px] text-sage">{candidateMeta(c)}</span>
            </span>
            <button
              type="button"
              onClick={() => resolve(c.tmdb_id)}
              disabled={pending}
              className="bg-orange px-4 py-2 font-display text-[12px] font-bold tracking-[.1em] text-green uppercase hover:bg-snow disabled:opacity-50 max-sm:col-start-2 max-sm:justify-self-start"
            >
              Match
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => resolve(null)}
        disabled={pending}
        className="mt-2.5 p-0 text-[13px] text-sage underline hover:text-orange disabled:opacity-50"
      >
        Not a film, reject
      </button>
      {error && <p className="mt-2 text-[13px]">{error}</p>}
    </div>
  );
}

function candidateMeta(c: Candidate) {
  return [c.year, c.director, c.runtime_minutes ? `${c.runtime_minutes} min` : null]
    .filter(Boolean)
    .join(" · ");
}

function formatScore(score: number) {
  return score.toFixed(2).replace(/^0\./, ".");
}
