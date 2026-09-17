import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export async function POST(req: Request) {
  // require real json so a cross-origin form post (text/plain, no preflight) can't land here
  const contentType = req.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return NextResponse.json({ error: "content-type must be application/json" }, { status: 400 });
  }

  let body: { id?: unknown; tracked?: unknown; isFavourite?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be json" }, { status: 400 });
  }

  const id = Number(body.id);
  if (!Number.isInteger(id)) {
    return NextResponse.json({ error: "id is required" }, { status: 400 });
  }
  if (body.tracked !== undefined && typeof body.tracked !== "boolean") {
    return NextResponse.json({ error: "tracked must be a boolean" }, { status: 400 });
  }
  if (body.isFavourite !== undefined && typeof body.isFavourite !== "boolean") {
    return NextResponse.json({ error: "isFavourite must be a boolean" }, { status: 400 });
  }

  const existing = await query<{ id: number }>("select id from theatre where id = $1", [id]);
  if (existing.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  if (body.tracked !== undefined) {
    await query("update theatre set tracked = $1 where id = $2", [body.tracked, id]);
  }
  if (body.isFavourite !== undefined) {
    await query("update theatre set is_favourite = $1 where id = $2", [body.isFavourite, id]);
  }
  return NextResponse.json({ ok: true });
}
