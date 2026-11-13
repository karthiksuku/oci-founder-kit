// Vault values are resolved only on the server, using its OCI resource principal.
import common from "oci-common";
import secrets from "oci-secrets";

export async function createSecretReader() {
  const provider = await common.ResourcePrincipalAuthenticationDetailsProvider.builder();
  const client = new secrets.SecretsClient({ authenticationDetailsProvider: provider });
  return secretReaderForClient(client);
}

export function secretReaderForClient(client) {
  return async (secretId, versionNumber) => {
    const result = await client.getSecretBundle({ secretId, ...(versionNumber ? { versionNumber } : { stage: "CURRENT" }) });
    const bundle = result.secretBundle?.secretBundleContent;
    if (bundle?.contentType !== "BASE64" || typeof bundle.content !== "string"
        || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(bundle.content)) {
      throw new Error("Secret content is invalid");
    }
    return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.from(bundle.content, "base64"));
  };
}

export async function resolveRuntimeConfig(config, readSecret) {
  if (config.mode !== "production") return config;
  try {
    const [oidcClientSecret, sessionSecret, databasePassword] = await Promise.all([
      readSecret(config.secretIds.oidc), readSecret(config.secretIds.session),
      readSecret(config.secretIds.database, config.databaseSecretVersion),
    ]);
    if (![oidcClientSecret, sessionSecret, databasePassword].every((value) => typeof value === "string" && value.length > 0)
        || Buffer.byteLength(sessionSecret) < 32) throw new Error("Invalid secret");
    return { ...config, oidcClientSecret, sessionSecret, database: { ...config.database, password: databasePassword } };
  } catch { throw new Error("Required runtime secrets could not be loaded; startup refused"); }
}
