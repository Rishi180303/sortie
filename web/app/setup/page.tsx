import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

type SettingRow = { key: string; value: string };

type TheatreRow = {
  id: number;
  name: string;
  distance_miles: number | null;
  tracked: boolean;
  is_favourite: boolean;
  upcoming: string; // postgres bigint comes back as a string
};

export default async function SetupPage() {
  const [settings, theatreRows] = await Promise.all([
    query<SettingRow>("select key, value from setting order by key"),
    query<TheatreRow>(`
      select t.id, t.name, t.distance_miles, t.tracked, t.is_favourite,
             count(*) filter (where s.show_date >= current_date) as upcoming
      from theatre t
      left join showing s on s.theatre_id = t.id
      group by t.id
      order by t.is_favourite desc, t.distance_miles nulls last
    `),
  ]);

  // postgres counts come back as strings, turn them into real numbers
  const theatres = theatreRows.map((t) => ({ ...t, upcoming: Number(t.upcoming) }));
  const tracked = theatres.filter((t) => t.tracked).length;
  const favourites = theatres.filter((t) => t.is_favourite).length;
  const upcoming = theatres.reduce((sum, t) => sum + t.upcoming, 0);

  return (
    <main>
      <div className="grid grid-cols-1 gap-6 pt-6 pb-8 sm:grid-cols-3">
        <Stat value={tracked} label="Cinemas tracked" />
        <Stat value={favourites} label="Favourites" />
        <Stat value={upcoming} label="Showings upcoming" />
      </div>

      <div className="sprocket thin" />

      <h2 className="mt-11 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        From the collector
      </h2>
      {settings.length === 0 ? (
        <p className="border-t border-line py-5 text-sage">
          The collector hasn&rsquo;t run yet — nothing recorded.
        </p>
      ) : (
        <div>
          {settings.map((s) => (
            <div
              key={s.key}
              className="flex items-baseline justify-between gap-4 border-t border-line py-3 hover:bg-green-2"
            >
              <span className="text-sage">{s.key.replaceAll("_", " ")}</span>
              <span className="num min-w-0 font-display font-semibold break-words text-right">
                {s.value}
              </span>
            </div>
          ))}
        </div>
      )}

      <h2 className="mt-11 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        Your cinemas
      </h2>
      <div>
        {theatres.map((t) => (
          <div key={t.id} className="border-t border-line py-4 hover:bg-green-2">
            <div className="font-display text-lg font-bold">
              {t.is_favourite && <span className="text-orange">&#9670; </span>}
              {t.name}
            </div>
            <div className="num mt-1 text-[13px] text-sage">
              {t.distance_miles !== null ? `${Math.round(t.distance_miles)} mi` : "unknown"}
              {" · "}
              {t.tracked ? "tracked" : "not tracked"}
              {" · "}
              {t.upcoming} upcoming
            </div>
          </div>
        ))}
      </div>
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
