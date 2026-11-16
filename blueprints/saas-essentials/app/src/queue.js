import common from "oci-common";
import queue from "oci-queue";

export class OciQueue {
  constructor(client, queueId) { this.client = client; this.queueId = queueId; }
  static async create(env) {
    const endpoint = new URL(env.OCI_QUEUE_ENDPOINT);
    if (endpoint.protocol !== "https:" || endpoint.username || endpoint.password || endpoint.port || endpoint.pathname !== "/" || endpoint.search || endpoint.hash
        || !/^[a-z0-9-]+\.queue\.messaging\.[a-z0-9-]+\.oci\.oraclecloud\.com$/.test(endpoint.hostname)
        || !/^ocid1\.queue\.[a-z0-9.-]+$/.test(env.OCI_QUEUE_ID ?? "")) throw new Error("Reviewed OCI Queue endpoint and ID required");
    const provider = await common.ResourcePrincipalAuthenticationDetailsProvider.builder();
    const client = new queue.QueueClient({ authenticationDetailsProvider: provider });
    client.endpoint = endpoint.origin;
    return new OciQueue(client, env.OCI_QUEUE_ID);
  }
  async send(content) {
    const result = await this.client.putMessages({ queueId: this.queueId, putMessagesDetails: { messages: [{ content }] } });
    if (!result.putMessages?.messages?.[0]?.id) throw new Error("Enqueue was not confirmed");
  }
  async receive() {
    const response = await this.client.getMessages({ queueId: this.queueId, limit: 1, timeoutInSeconds: 20, visibilityInSeconds: 60 });
    return response.getMessages.messages;
  }
  async renew(receipt, visibilityInSeconds) {
    await this.client.updateMessage({ queueId: this.queueId, messageReceipt: receipt, updateMessageDetails: { visibilityInSeconds } });
  }
  async remove(receipt) {
    await this.client.deleteMessage({ queueId: this.queueId, messageReceipt: receipt });
  }
}
