import pg from "pg";
import { fileURLToPath } from "node:url";
import { createApp } from "../../../fullstack-container/app/src/app.js";
import { createAuth } from "../../../fullstack-container/app/src/auth.js";
import { loadConfig } from "../../../fullstack-container/app/src/config.js";
import { createSecretReader, resolveRuntimeConfig } from "../../../fullstack-container/app/src/secrets.js";
import { OciAttachmentStore } from "../../../fullstack-container/app/src/stores/oci-attachment-store.js";
import { JobStore, RequestStore } from "./store.js";
import { webhookRoutes } from "./webhook.js";

async function main() {
  const initial = loadConfig(process.env);
  const secretReader = initial.mode === "production" ? await createSecretReader() : null;
  const config = await resolveRuntimeConfig(initial, secretReader);
  const pool = new pg.Pool({ ...(config.mode === "production" ? config.database : { connectionString: config.databaseUrl }),
    ssl: config.databaseTls, max: 10, connectionTimeoutMillis: 10000 });
  const jobs = new JobStore(pool, process.env.SAAS_ENVIRONMENT);
  const tasks = new RequestStore(pool, jobs);
  // Schema/ownership setup is a separate, reviewed operation; startup does not migrate production data.
  await tasks.ping();
  const auth = config.mode === "production" ? await createAuth({ config, pool }) : null;
  const attachments = config.storage ? await OciAttachmentStore.create(config.storage) : null;
  if (config.mode === "production" && process.env.WEBHOOK_SECRET) throw new Error("Webhook secret must come from Vault");
  const secret = config.mode === "production" ? await secretReader(process.env.WEBHOOK_SECRET_OCID) : process.env.WEBHOOK_SECRET;
  const app = createApp({ tasks, attachments, config, auth,
    publicDirectory: fileURLToPath(new URL("../public", import.meta.url)),
    mountBeforeBody: webhookRoutes({ jobs, secret, owner: process.env.WEBHOOK_OWNER_ID }),
    mountApi: (router) => router.get("/api/jobs", async (req, res) => res.json(await jobs.jobs(req.ownerId))) });
  const server = app.listen(config.port, config.host);
  const stop = () => { server.close(() => pool.end()); setTimeout(() => process.exit(1), 10000).unref(); };
  process.on("SIGTERM", stop); process.on("SIGINT", stop);
}
main().catch(() => { process.stderr.write("SaaS startup failed; inspect private configuration and schema readiness.\n"); process.exitCode = 1; });
