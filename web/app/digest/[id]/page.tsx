import { notFound } from "next/navigation";
import { isId, query } from "@/lib/db";

export const dynamic = "force-dynamic";

type DigestRow = { id: number; sent_at: Date; subject: string; html_body: string };

export default async function DigestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const digestId = Number(id); // a url segment is always a string, so this stays
  if (!isId(digestId)) notFound();

  const rows = await query<DigestRow>(
    "select id, sent_at, subject, html_body from digest where id = $1",
    [digestId]
  );
  const digest = rows[0];
  if (!digest) notFound();

  return (
    <main>
      <div className="pt-6 pb-8">
        <div className="font-display text-[clamp(22px,3.2vw,30px)] leading-[1.05] font-bold tracking-tight">
          {digest.subject}
        </div>
        <div className="mt-1.5 text-[13px] text-sage">{formatDateTime(digest.sent_at)}</div>
      </div>

      <div className="sprocket thin" />

      <h2 className="mt-11 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        The email
      </h2>

      {/* html_body does carry scraped theatre names, film titles and error strings, but
          render_html (sortie/alerts/digest.py) escapes every one of those before writing
          them into html, see tests/test_digest.py, so rendering it straight in is safe.
          the snow band stays: the stored email's own background is the same rifle green
          as this page, so without it you could not see where the sent email starts */}
      <div className="-mx-[22px] bg-snow px-[22px] py-10">
        <div dangerouslySetInnerHTML={{ __html: digest.html_body }} />
      </div>
    </main>
  );
}

function formatDateTime(d: Date) {
  return new Date(d).toLocaleString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}
