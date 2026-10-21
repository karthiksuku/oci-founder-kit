// Entry point: read configuration, connect stores, migrate the schema, serve.

import pg from "pg";
import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { logger } from "./logger.js";
import { PgTaskStore } from "./stores/pg-task-store.js";
import { OciAttachmentStore } from "./stores/oci-attachment-store.js";

async function main() {
  const config = loadConfig(process.env);
  const pool = new pg.Pool({
    connectionString: config.databaseUrl,
    max: 10,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 10_000,
    ssl: config.databaseTls,
  });
  pool.on("error", (err) => logger.error("idle database client error", { error: err.message }));
  const tasks = new PgTaskStore(pool);
  await tasks.migrate();
  const attachments = config.storage ? await OciAttachmentStore.create(config.storage) : null;
  if (!attachments) logger.warn("file storage is off: set OCI_BUCKET and OCI_NAMESPACE to enable attachments");

  const server = createApp({ tasks, attachments, config }).listen(config.port, config.host, () => {
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

main().catch((err) => {
  logger.error("startup failed", { error: err.message });
  process.exit(1);
});
