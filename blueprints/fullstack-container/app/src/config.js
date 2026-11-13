// Configuration is explicit: production cannot fall back to sandbox credentials.
import { isIP } from "node:net";

function required(env, name) {
  if (typeof env[name] !== "string" || !env[name].trim()) throw new Error(`${name} is required`);
  return env[name];
}
function httpsUrl(value, name, originOnly = false) {
  let url;
  try { url = new URL(value); } catch { throw new Error(`${name} must be an HTTPS URL`); }
  if (url.protocol !== "https:" || url.username || url.password || url.hash || url.search
      || (originOnly && url.pathname !== "/")) throw new Error(`${name} must be an HTTPS ${originOnly ? "origin" : "URL"}`);
  return originOnly ? url.origin : url.href;
}
function secretId(env, name) {
  const value = required(env, name);
  if (!/^ocid1\.vaultsecret\.[a-z0-9]+\.[a-z0-9-]*\.[a-z0-9]+$/.test(value)) throw new Error(`${name} must be a secret OCID`);
  return value;
}
function integer(env, name, fallback, max = 65535) {
  const value = Number(env[name] ?? fallback);
  if (!Number.isSafeInteger(value) || value < 1 || value > max) throw new Error(`${name} must be a positive whole number`);
  return value;
}
export function loadConfig(env) {
  if (!["sandbox", "production"].includes(env.APP_MODE)) throw new Error("APP_MODE must be explicitly sandbox or production");
  const production = env.APP_MODE === "production";
  const config = {
    mode: env.APP_MODE, host: env.HOST || "127.0.0.1", port: integer(env, "PORT", 8080),
    maxUploadBytes: integer(env, "MAX_UPLOAD_BYTES", 10 * 1024 * 1024, 10 * 1024 * 1024),
    databaseTls: env.DATABASE_CA_CERT ? { rejectUnauthorized: true, ca: env.DATABASE_CA_CERT } : { rejectUnauthorized: true },
    storage: env.OCI_BUCKET && env.OCI_NAMESPACE ? { bucket: env.OCI_BUCKET, namespace: env.OCI_NAMESPACE,
      region: env.OCI_REGION ?? null, auth: env.OCI_AUTH === "config-file" ? "config-file" : "resource-principal" } : null,
  };
  if (!production) {
    config.databaseUrl = required(env, "DATABASE_URL");
    if (env.DATABASE_SSL === "false") config.databaseTls = false;
    return config;
  }
  if (env.DATABASE_URL || env.DATABASE_SSL === "false" || (env.OCI_AUTH && env.OCI_AUTH !== "resource-principal")
      || env.OIDC_CLIENT_SECRET || env.SESSION_SECRET || env.DATABASE_PASSWORD) {
    throw new Error("Production requires resource principals, Vault secrets and verified database TLS");
  }
  if (Boolean(env.OCI_BUCKET) !== Boolean(env.OCI_NAMESPACE)) throw new Error("Configure both OCI_BUCKET and OCI_NAMESPACE");
  config.publicOrigin = httpsUrl(required(env, "PUBLIC_ORIGIN"), "PUBLIC_ORIGIN", true);
  config.oidcIssuer = httpsUrl(required(env, "OIDC_ISSUER"), "OIDC_ISSUER");
  if (env.OIDC_DISCOVERY_URL) config.oidcDiscoveryUrl = httpsUrl(env.OIDC_DISCOVERY_URL, "OIDC_DISCOVERY_URL");
  config.oidcClientId = required(env, "OIDC_CLIENT_ID");
  config.secretIds = { oidc: secretId(env, "OIDC_CLIENT_SECRET_OCID"), session: secretId(env, "SESSION_SECRET_OCID"),
    database: secretId(env, "DATABASE_PASSWORD_SECRET_OCID") };
  config.databaseSecretVersion = integer(env, "DATABASE_PASSWORD_SECRET_VERSION", 1, 2147483647);
  config.database = { host: required(env, "DATABASE_HOST"), port: integer(env, "DATABASE_PORT", 5432),
    database: required(env, "DATABASE_NAME"), user: required(env, "DATABASE_USER") };
  config.databaseTls = { rejectUnauthorized: true, ca: required(env, "DATABASE_CA_CERT") };
  config.trustProxy = required(env, "TRUST_PROXY_CIDRS").split(",").map((part) => part.trim());
  if (!config.trustProxy.every((cidr) => {
    const [address, prefix, extra] = cidr.split("/");
    const version = isIP(address);
    return version && !extra && /^\d+$/.test(prefix ?? "") && Number(prefix) > 0 && Number(prefix) <= (version === 4 ? 32 : 128);
  })) throw new Error("TRUST_PROXY_CIDRS must contain specific trusted proxy CIDRs");
  return config;
}
