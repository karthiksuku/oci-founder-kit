// A Taskboard mountApi extension. Identity and CSRF verification belong to the host.
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";

const base = "/api/b2b";
const org = base + "/organizations/:org";
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const owner = /^[a-f0-9]{64}$/;
const roles = new Set(["admin", "member"]);
const exportLimit = 1000;
const hash = (token) => createHash("sha256").update(token).digest("hex");
const view = (name) => fileURLToPath(new URL(name, import.meta.url));

class Fault extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}
function text(value, limit) {
  if (typeof value !== "string" || !value.trim() || value.trim().length > limit) {
    throw new Fault(400, "Enter a value within the field length limit.");
  }
  return value.trim();
}
function recipient(value) {
  if (typeof value !== "string" || !owner.test(value)) throw new Fault(400, "Enter the recipient's workspace ID.");
  return value;
}
function role(value) {
  if (!roles.has(value)) throw new Fault(400, "Choose admin or member.");
  return value;
}
async function transaction(pool, fn) {
  const db = await pool.connect();
  let rollbackFailed = false;
  try {
    await db.query("BEGIN ISOLATION LEVEL READ COMMITTED");
    const result = await fn(db);
    await db.query("COMMIT");
    return result;
  } catch (err) {
    try { await db.query("ROLLBACK"); } catch { rollbackFailed = true; }
    throw err;
  } finally {
    db.release(rollbackFailed);
  }
}

export function workspaceRoutes({ pool, config }) {
  if (config?.mode !== "production" || !pool) throw new Error("Workspace requires the production OIDC session and database pool.");
  return (app) => {
    app.use(base, (req, res, next) => {
      const user = req.session?.user;
      if (!user || !Number.isFinite(user.expiresAt) || user.expiresAt <= Date.now()
          || typeof user.owner !== "string" || !owner.test(user.owner) || req.ownerId !== user.owner) {
        return res.status(401).json({ error: "Sign in to the workspace." });
      }
      res.set("Cache-Control", "no-store");
      next();
    });
    app.get(base + "/portal", (_req, res) => res.sendFile(view("portal.html"), { cacheControl: false }));
    app.get(base + "/portal.css", (_req, res) => res.sendFile(view("portal.css"), { cacheControl: false }));
    app.get(base + "/portal.mjs", (_req, res) => res.sendFile(view("portal.mjs"), { cacheControl: false }));
    app.get(base + "/me", async (req, res) => {
      const result = await pool.query(
        `SELECT o.id, o.name, m.role FROM founder_workspace.memberships m
         JOIN founder_workspace.organizations o ON o.id=m.organization_id
         WHERE m.user_id=$1 ORDER BY o.name, o.id`, [req.ownerId]);
      res.json({ recipientId: req.ownerId, organizations: result.rows });
    });
    app.post(base + "/organizations", async (req, res) => {
      const name = text(req.body?.name, 120);
      const id = randomUUID();
      await transaction(pool, async (db) => {
        await db.query("INSERT INTO founder_workspace.organizations(id, name) VALUES ($1, $2)", [id, name]);
        await db.query("INSERT INTO founder_workspace.memberships VALUES ($1, $2, 'admin')", [id, req.ownerId]);
      });
      res.status(201).json({ id, name });
    });

    // A shared/read or exclusive/write lock orders reads, invite changes and revocation.
    // Re-read membership after the lock to observe a concurrent administrator's commit.
    function scoped(level, fn) {
      return async (req, res) => {
        const id = req.params.org;
        if (!uuid.test(id)) throw new Fault(404, "Workspace unavailable.");
        const result = await transaction(pool, async (db) => {
          const lock = req.method === "GET" || req.method === "HEAD" ? "FOR SHARE" : "FOR UPDATE";
          const exists = await db.query("SELECT id FROM founder_workspace.organizations WHERE id=$1 " + lock, [id]);
          if (!exists.rowCount) throw new Fault(404, "Workspace unavailable.");
          if (level !== "invitee") {
            const member = await db.query(
              "SELECT role FROM founder_workspace.memberships WHERE organization_id=$1 AND user_id=$2", [id, req.ownerId]);
            if (!member.rowCount) throw new Fault(404, "Workspace unavailable.");
            if (level === "admin" && member.rows[0].role !== "admin") throw new Fault(403, "An administrator is required.");
          }
          return fn(db, req, id);
        });
        res.status(req.method === "POST" ? 201 : 200).json(result);
      };
    }

    app.get(org + "/access", scoped("admin", async (db, _req, id) => {
      const members = await db.query("SELECT user_id, role FROM founder_workspace.memberships WHERE organization_id=$1 ORDER BY user_id", [id]);
      const invitations = await db.query(
        "SELECT id, recipient, role, expires_at FROM founder_workspace.invitations WHERE organization_id=$1 AND expires_at>clock_timestamp() ORDER BY expires_at", [id]);
      return { members: members.rows, invitations: invitations.rows };
    }));
    app.post(org + "/invitations", scoped("admin", async (db, req, id) => {
      const target = recipient(req.body?.recipient);
      const member = await db.query("SELECT 1 FROM founder_workspace.memberships WHERE organization_id=$1 AND user_id=$2", [id, target]);
      if (member.rowCount) throw new Fault(409, "This account already belongs to the organization.");
      const token = randomBytes(32).toString("base64url");
      const created = await db.query(
        `INSERT INTO founder_workspace.invitations (id, organization_id, issued_by, recipient, role, token_hash, expires_at)
         VALUES ($1,$2,$3,$4,$5,$6,clock_timestamp()+interval '48 hours')
         ON CONFLICT (organization_id,recipient) DO UPDATE SET
           id=excluded.id, issued_by=excluded.issued_by, role=excluded.role, token_hash=excluded.token_hash, expires_at=excluded.expires_at
         RETURNING id, expires_at`, [randomUUID(), id, req.ownerId, target, role(req.body?.role), hash(token)]);
      return { ...created.rows[0], organization: id, token };
    }));
    app.post(org + "/accept", scoped("invitee", async (db, req, id) => {
      const token = req.body?.token;
      if (typeof token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Fault(404, "Workspace unavailable.");
      const invite = await db.query(
        `DELETE FROM founder_workspace.invitations WHERE organization_id=$1 AND recipient=$2
         AND token_hash=$3 AND expires_at>clock_timestamp() RETURNING role`, [id, req.ownerId, hash(token)]);
      if (!invite.rowCount) throw new Fault(404, "Workspace unavailable.");
      await db.query("INSERT INTO founder_workspace.memberships VALUES ($1, $2, $3)", [id, req.ownerId, invite.rows[0].role]);
      return { joined: true };
    }));
    app.delete(org + "/invitations/:id", scoped("admin", async (db, req, id) => {
      if (!uuid.test(req.params.id)) throw new Fault(404, "Invitation unavailable.");
      const removed = await db.query("DELETE FROM founder_workspace.invitations WHERE organization_id=$1 AND id=$2", [id, req.params.id]);
      if (!removed.rowCount) throw new Fault(404, "Invitation unavailable.");
      return { revoked: true };
    }));
    const manageMember = scoped("admin", async (db, req, id) => {
      const target = recipient(req.params.member);
      const nextRole = req.method === "PATCH" ? role(req.body?.role) : null;
      const current = await db.query("SELECT role FROM founder_workspace.memberships WHERE organization_id=$1 AND user_id=$2", [id, target]);
      if (!current.rowCount) throw new Fault(404, "Membership unavailable.");
      if (current.rows[0].role === "admin" && nextRole !== "admin") {
        const other = await db.query("SELECT 1 FROM founder_workspace.memberships WHERE organization_id=$1 AND user_id<>$2 AND role='admin' LIMIT 1", [id, target]);
        if (!other.rowCount) throw new Fault(409, "Assign another administrator first.");
        await db.query("DELETE FROM founder_workspace.invitations WHERE organization_id=$1 AND issued_by=$2", [id, target]);
      }
      if (nextRole) {
        await db.query("UPDATE founder_workspace.memberships SET role=$3 WHERE organization_id=$1 AND user_id=$2", [id, target, nextRole]);
        return { role: nextRole };
      }
      await db.query("DELETE FROM founder_workspace.invitations WHERE organization_id=$1 AND recipient=$2", [id, target]);
      await db.query("DELETE FROM founder_workspace.memberships WHERE organization_id=$1 AND user_id=$2", [id, target]);
      return { removed: true };
    });
    app.patch(org + "/members/:member", manageMember);
    app.delete(org + "/members/:member", manageMember);

    app.post(org + "/requests", scoped("member", async (db, req, id) => {
      const created = await db.query(
        "INSERT INTO founder_workspace.requests (id,organization_id,title) VALUES ($1,$2,$3) RETURNING id,title,created_at",
        [randomUUID(), id, text(req.body?.title, 200)]);
      return created.rows[0];
    }));
    app.get(org + "/requests/:id", scoped("member", async (db, req, id) => {
      if (!uuid.test(req.params.id)) throw new Fault(404, "Request unavailable.");
      const result = await db.query("SELECT id,title,created_at FROM founder_workspace.requests WHERE organization_id=$1 AND id=$2", [id, req.params.id]);
      if (!result.rowCount) throw new Fault(404, "Request unavailable.");
      return result.rows[0];
    }));
    app.get(org + "/requests", scoped("member", async (db, _req, id) => {
      const result = await db.query("SELECT id,title,created_at FROM founder_workspace.requests WHERE organization_id=$1 ORDER BY created_at DESC, id LIMIT 100", [id]);
      return { requests: result.rows };
    }));
    app.get(org + "/export", scoped("admin", async (db, _req, id) => {
      const result = await db.query("SELECT id,title,created_at FROM founder_workspace.requests WHERE organization_id=$1 ORDER BY created_at,id LIMIT $2", [id, exportLimit + 1]);
      if (result.rowCount > exportLimit) throw new Fault(409, "Export exceeds the starter limit. Use a reviewed paginated export.");
      return { schema: "founder-workspace-export/1", organization: id, requests: result.rows };
    }));
    app.use(base, (err, _req, res, next) => {
      if (err instanceof Fault) return res.status(err.status).json({ error: err.message });
      next(err);
    });
  };
}
