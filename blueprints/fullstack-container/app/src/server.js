// Entry point: read configuration, connect stores, migrate the schema, serve.

import pg from "pg";
import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createAuth } from "./auth.js";
import { createSecretReader, resolveRuntimeConfig } from "./secrets.js";
import { logger } from "./logger.js";
import { PgTaskStore } from "./stores/pg-task-store.js";
import { OciAttachmentStore } from "./stores/oci-attachment-store.js";

async function main() {
  const initialConfig = loadConfig(process.env);
  const config = await resolveRuntimeConfig(initialConfig,
    initialConfig.mode === "production" ? await createSecretReader() : null);
  const pool = new pg.Pool({
    ...(config.mode === "production" ? config.database : { connectionString: config.databaseUrl }),
    max: 10,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 10_000,
    ssl: config.databaseTls,
  });
  pool.on("error", () => logger.error("idle database client error"));
  const tasks = new PgTaskStore(pool);
  await tasks.migrate();
  const attachments = config.storage ? await OciAttachmentStore.create(config.storage) : null;
  if (!attachments) logger.warn("file storage is off: set OCI_BUCKET and OCI_NAMESPACE to enable attachments");

  const auth = config.mode === "production" ? await createAuth({ config, pool }) : null;
  const server = createApp({ tasks, attachments, config, auth }).listen(config.port, config.host, () => {
    logger.info("taskboard listening", { host: config.host, port: config.port, storage: Boolean(attachments) });
  });

  const shutdown = (signal) => {
    logger.info("shutting down", { signal });
    server.close(() => pool.end().finally(() => process.exit(0)));
    setTimeout(() => process.exit(1), 10_000).unref();
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

main().catch(() => {
  logger.error("startup failed; verify configuration and access privately");
  process.exit(1);
});
