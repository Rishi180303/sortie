import Link from "next/link";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

type SummaryRow = { total: string; alerts: string };
type DigestRow = { id: number; sent_at: Date; subject: string; alert_count: number };

export default async function DigestListPage() {
  const [summaryRows, digests] = await Promise.all([
    query<SummaryRow>("select count(*) as total, coalesce(sum(alert_count), 0) as alerts from digest"),
    query<DigestRow>(
      "select id, sent_at, subject, alert_count from digest order by sent_at desc limit 60"
    ),
  ]);

  const summary = summaryRows[0];
  const total = Number(summary.total);
  const alerts = Number(summary.alerts);

  return (
    <main>
      <div className="grid grid-cols-1 gap-6 pt-6 pb-8 sm:grid-cols-2">
        <Stat value={total} label="Digests sent" />
        <Stat value={alerts} label="Alerts sent" />
      </div>

      <div className="sprocket thin" />

      <h2 className="mt-11 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        History
      </h2>

      {digests.length === 0 ? (
        <p className="border-t border-line py-5 text-sage">
          No digest has been sent yet. The collector writes one here every time it emails.
        </p>
      ) : (
        <div>
          {digests.map((d) => (
            <Link
              key={d.id}
              href={`/digest/${d.id}`}
              className="block border-t border-line py-[22px] text-snow no-underline hover:bg-green-2"
            >
              <div className="font-display text-[clamp(22px,3.2vw,30px)] leading-[1.05] font-bold tracking-tight">
                {d.subject}
              </div>
              <div className="mt-1.5 text-[13px] text-sage">
                {formatDateTime(d.sent_at)} · {d.alert_count} {d.alert_count === 1 ? "alert" : "alerts"}
              </div>
            </Link>
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
