import pg from "pg";
import { createSecretReader } from "../../../fullstack-container/app/src/secrets.js";

export async function workerPool(env) {
  if (!["sandbox", "production"].includes(env.APP_MODE)) throw new Error("Explicit APP_MODE required");
  if (env.APP_MODE === "sandbox") {
    const url = new URL(env.DATABASE_URL);
    if (!["127.0.0.1", "localhost", "[::1]", "db"].includes(url.hostname)) throw new Error("Sandbox database must be local");
    return new pg.Pool({ connectionString: env.DATABASE_URL, ssl: false, max: 5, connectionTimeoutMillis: 10000 });
  }
  if (env.DATABASE_URL || env.DATABASE_PASSWORD || env.DATABASE_SSL === "false") throw new Error("Use Vault and verified TLS");
  for (const field of ["DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_CA_CERT", "DATABASE_PASSWORD_SECRET_OCID"]) {
    if (!env[field]) throw new Error("Missing worker database configuration");
  }
  if (!/^ocid1\.vaultsecret\.[a-z0-9.-]+$/.test(env.DATABASE_PASSWORD_SECRET_OCID)) throw new Error("Invalid database secret reference");
  const secret = await createSecretReader();
  return new pg.Pool({ host: env.DATABASE_HOST, port: 5432, database: env.DATABASE_NAME, user: env.DATABASE_USER,
    password: await secret(env.DATABASE_PASSWORD_SECRET_OCID), ssl: { rejectUnauthorized: true, ca: env.DATABASE_CA_CERT }, max: 5,
    connectionTimeoutMillis: 10000, statement_timeout: 30000, query_timeout: 35000 });
}
