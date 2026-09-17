import { NextResponse } from "next/server";
import { transaction } from "@/lib/db";

export async function POST(req: Request) {
  // require real json so a cross-origin form post (text/plain, no preflight) can't land here
  const contentType = req.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return NextResponse.json({ error: "content-type must be application/json" }, { status: 400 });
  }

  let body: { queueId?: unknown; tmdbId?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be json" }, { status: 400 });
  }

  const queueId = Number(body.queueId);
  if (!Number.isInteger(queueId)) {
    return NextResponse.json({ error: "queueId is required" }, { status: 400 });
  }

  const tmdbId = body.tmdbId === null ? null : Number(body.tmdbId);
  if (tmdbId !== null && !Number.isInteger(tmdbId)) {
    return NextResponse.json({ error: "tmdbId must be a number or null" }, { status: 400 });
  }

  let outcome: "resolved" | "not_found" | "invalid_candidate";
  try {
    // one transaction: source_film and match_queue always move together, never half-done
    outcome = await transaction(async (client) => {
      const rows = await client.query<{ source_film_id: number; candidates: { tmdb_id: number }[] }>(
        "select source_film_id, candidates from match_queue where id = $1 and resolved_at is null for update",
        [queueId]
      );
      if (rows.rows.length === 0) return "not_found";
      const { source_film_id: sourceFilmId, candidates } = rows.rows[0];

      if (tmdbId !== null) {
        // only allow matching to a film the collector actually offered for this row
        const offered = candidates.some((c) => c.tmdb_id === tmdbId);
        if (!offered) return "invalid_candidate";
        // a person chose this, so it outranks any score the collector computed
        await client.query(
          "update source_film set tmdb_id = $1, resolution = 'manual', confidence = 1.0, resolved_at = now() where id = $2",
          [tmdbId, sourceFilmId]
        );
      } else {
        await client.query(
          "update source_film set resolution = 'rejected', resolved_at = now() where id = $1",
          [sourceFilmId]
        );
      }
      await client.query("update match_queue set resolved_at = now() where id = $1", [queueId]);
      return "resolved";
    });
  } catch {
    // a db-level failure (bad id, out-of-range int, etc), never leak the db's own error text
    return NextResponse.json({ error: "something went wrong" }, { status: 500 });
  }

  if (outcome === "not_found") {
    return NextResponse.json({ error: "not found or already resolved" }, { status: 404 });
  }
  if (outcome === "invalid_candidate") {
    return NextResponse.json({ error: "tmdbId is not one of this row's candidates" }, { status: 400 });
  }
  return NextResponse.json({ ok: true });
}
