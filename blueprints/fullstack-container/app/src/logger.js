// Structured JSON logs on stdout and stderr, which OCI Logging can ingest as is.

/**
 * @param {"info" | "warn" | "error"} level
 * @param {string} message
 * @param {Record<string, unknown>} [fields]
 */
function write(level, message, fields = {}) {
  const line = JSON.stringify({ time: new Date().toISOString(), level, message, ...fields }) + "\n";
  (level === "error" ? process.stderr : process.stdout).write(line);
}

export const logger = {
  info: (message, fields) => write("info", message, fields),
  warn: (message, fields) => write("warn", message, fields),
  error: (message, fields) => write("error", message, fields),
};
