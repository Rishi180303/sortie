import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Home() {
  const rows = await query<{ key: string; value: string }>(
    "select key, value from setting order by key"
  );
  return (
    <main>
      <h1>sortie</h1>
      <ul>
        {rows.map((r) => (
          <li key={r.key}>
            {r.key}: {r.value}
          </li>
        ))}
      </ul>
    </main>
  );
}
