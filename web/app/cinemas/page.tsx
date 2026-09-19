import { query } from "@/lib/db";
import { TheatreToggle } from "./theatre-toggles";

export const dynamic = "force-dynamic";

type TheatreRow = {
  id: number;
  name: string;
  distance_miles: number | null;
  tracked: boolean;
  is_favourite: boolean;
};

export default async function CinemasPage() {
  const theatres = await query<TheatreRow>(`
    select id, name, distance_miles, tracked, is_favourite
    from theatre
    order by is_favourite desc, distance_miles nulls last
  `);

  return (
    <main>
      <h2 className="pt-6 mb-4 font-display text-[13px] font-extrabold tracking-[.2em] text-orange uppercase">
        Your cinemas
      </h2>
      <div>
        {theatres.map((t) => (
          <TheatreToggle key={t.id} theatre={t} />
        ))}
      </div>
    </main>
  );
}
