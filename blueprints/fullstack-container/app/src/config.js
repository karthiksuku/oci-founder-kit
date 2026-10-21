// Configuration from environment variables, validated at startup.

/**
 * @typedef {{ bucket: string, namespace: string, region: string | null, auth: "resource-principal" | "config-file" }} StorageConfig
 * @typedef {{ rejectUnauthorized: true, ca?: string } | false} DatabaseTls
 * @typedef {{ host: string, port: number, databaseUrl: string, databaseTls: DatabaseTls, storage: StorageConfig | null, maxUploadBytes: number }} Config
 */

/**
 * Read and validate configuration. Throws with a message that never echoes secrets.
 * @param {Record<string, string | undefined>} env
 * @returns {Config}
 */
export function loadConfig(env) {
  if (!env.DATABASE_URL) {
    throw new Error("DATABASE_URL is required, for example postgres://user:password@host:5432/taskboard");
  }
  const port = Number(env.PORT ?? 8080);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be a number between 1 and 65535");
  }
  const maxUploadBytes = Number(env.MAX_UPLOAD_BYTES ?? 10 * 1024 * 1024);
  if (!Number.isInteger(maxUploadBytes) || maxUploadBytes < 1) {
    throw new Error("MAX_UPLOAD_BYTES must be a positive whole number");
  }
  const storage = env.OCI_BUCKET && env.OCI_NAMESPACE
    ? {
        bucket: env.OCI_BUCKET,
        namespace: env.OCI_NAMESPACE,
        region: env.OCI_REGION ?? null,
        auth: env.OCI_AUTH === "config-file" ? "config-file" : "resource-principal",
      }
    : null;
  // TLS always verifies the server certificate; DATABASE_CA_CERT supplies the
  // database's CA (OCI Database with PostgreSQL publishes it). There is no
  // insecure mode. DATABASE_SSL=false is for a local database only.
  let databaseTls = false;
  if (env.DATABASE_SSL !== "false") {
    databaseTls = env.DATABASE_CA_CERT
      ? { rejectUnauthorized: true, ca: env.DATABASE_CA_CERT }
      : { rejectUnauthorized: true };
  }
  return {
    // Loopback by default. On OCI the container sets HOST so the load
    // balancer can reach it inside the private subnet.
    host: env.HOST || "127.0.0.1",
    port,
    databaseUrl: env.DATABASE_URL,
    databaseTls,
    storage,
    maxUploadBytes,
  };
}
