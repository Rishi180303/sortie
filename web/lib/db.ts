import { Pool } from "pg";

// one pool per lambda, vercel reuses the module between invocations
const globalForPool = globalThis as unknown as { pool?: Pool };

const pool =
  globalForPool.pool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 3,
    idleTimeoutMillis: 10_000,
  });

if (!globalForPool.pool) globalForPool.pool = pool;

export async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const result = await pool.query(sql, params);
  return result.rows as T[];
}
