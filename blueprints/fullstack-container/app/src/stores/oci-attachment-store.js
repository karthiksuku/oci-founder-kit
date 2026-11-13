// Attachments in OCI Object Storage through short-lived pre-authenticated requests.
// On OCI the container authenticates as a resource principal: no keys are stored.
// For local development, OCI_AUTH=config-file uses ~/.oci/config instead.

import common from "oci-common";
import objectstorage from "oci-objectstorage";

const UPLOAD_MINUTES = 10;
const DOWNLOAD_MINUTES = 5;

/** @param {"resource-principal" | "config-file"} auth */
async function authProvider(auth) {
  if (auth === "config-file") {
    return new common.ConfigFileAuthenticationDetailsProvider(undefined, process.env.OCI_CONFIG_PROFILE);
  }
  return common.ResourcePrincipalAuthenticationDetailsProvider.builder();
}

export class OciAttachmentStore {
  /**
   * @param {objectstorage.ObjectStorageClient} client
   * @param {{ bucket: string, namespace: string, region: string }} settings
   */
  constructor(client, settings) {
    this.client = client;
    this.settings = settings;
  }

  /** @param {{ bucket: string, namespace: string, region: string | null, auth: "resource-principal" | "config-file" }} storage */
  static async create(storage) {
    const provider = await authProvider(storage.auth);
    const client = new objectstorage.ObjectStorageClient({ authenticationDetailsProvider: provider });
    const region = storage.region ?? (typeof provider.getRegion === "function" ? provider.getRegion()?.regionId : null);
    if (!region) throw new Error("OCI_REGION is required when the auth provider does not supply a region");
    client.regionId = region;
    return new OciAttachmentStore(client, { bucket: storage.bucket, namespace: storage.namespace, region });
  }

  /** @param {string} objectName @param {"ObjectWrite" | "ObjectRead"} accessType @param {number} minutes */
  async #par(objectName, accessType, minutes) {
    const expires = new Date(Date.now() + minutes * 60_000);
    const response = await this.client.createPreauthenticatedRequest({
      namespaceName: this.settings.namespace,
      bucketName: this.settings.bucket,
      createPreauthenticatedRequestDetails: {
        name: `taskboard-${accessType}-${Date.now()}`,
        objectName,
        accessType: objectstorage.models.CreatePreauthenticatedRequestDetails.AccessType[accessType],
        timeExpires: expires,
      },
    });
    const par = response.preauthenticatedRequest;
    const url = par.fullPath ?? `https://objectstorage.${this.settings.region}.oraclecloud.com${par.accessUri}`;
    return { url, expiresAt: expires.toISOString() };
  }

  /** @param {string} objectName */
  async createUploadUrl(objectName) {
    return this.#par(objectName, "ObjectWrite", UPLOAD_MINUTES);
  }

  /** @param {string} objectName */
  async createDownloadUrl(objectName) {
    return (await this.#par(objectName, "ObjectRead", DOWNLOAD_MINUTES)).url;
  }

  async put(objectName, body) {
    await this.client.putObject({ namespaceName: this.settings.namespace, bucketName: this.settings.bucket,
      objectName, putObjectBody: body, contentLength: body.length, contentType: "application/octet-stream" });
  }

  async get(objectName) {
    const result = await this.client.getObject({ namespaceName: this.settings.namespace,
      bucketName: this.settings.bucket, objectName });
    return result.value;
  }

}
