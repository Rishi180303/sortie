import { Pool } from "pg";
import type { PoolClient } from "pg";

// one pool per lambda, vercel reuses the module between invocations
const globalForPool = globalThis as unknown as { pool?: Pool };

const pool =
  globalForPool.pool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 3,
    idleTimeoutMillis: 10_000,
    // generous on purpose: neon's free tier suspends idle compute, so a cold start
    // can take a few seconds instead of hanging until the whole function times out
    connectionTimeoutMillis: 10_000,
  });

if (!globalForPool.pool) {
  // an idle socket can be reset while the lambda is frozen; with no listener that
  // unhandled 'error' event crashes the instance
  pool.on("error", (err) => console.error(err));
  globalForPool.pool = pool;
}

// true only for an int postgres can store in an int4 column (max is 2^31 - 1)
export function isId(v: unknown): v is number {
  if (typeof v !== "number") return false;
  if (!Number.isInteger(v)) return false;
  if (v < 1) return false;
  if (v > 2147483647) return false;
  return true;
}

export async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const result = await pool.query(sql, params);
  return result.rows as T[];
}

// run a few statements on one connection, so a multi-step write can't land half-done
export async function transaction<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query("begin");
    const result = await fn(client);
    await client.query("commit");
    return result;
  } catch (err) {
    await client.query("rollback");
    throw err;
  } finally {
    client.release();
  }
}
