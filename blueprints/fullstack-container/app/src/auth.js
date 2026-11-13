// OIDC proof remains server-side. A stable owner key uses issuer + subject, never email.
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import session from "express-session";
import connectPgSimple from "connect-pg-simple";
import * as oidc from "openid-client";
import { logger } from "./logger.js";

const IDLE_MS = 30 * 60_000;
const ABSOLUTE_MS = 8 * 60 * 60_000;
const LOGIN_MS = 5 * 60_000;
export const COOKIE_NAME = "__Host-taskboard";
const token = () => randomBytes(32).toString("base64url");
const callSession = (req, method) => new Promise((resolve, reject) => req.session[method]((err) => err ? reject(err) : resolve()));
export const ownerKey = (issuer, subject) => createHash("sha256").update(JSON.stringify([issuer, subject])).digest("hex");

export async function createAuth({ config, pool, store, oidcConfiguration, discoveryOptions }) {
  if (config.mode !== "production" || !config.sessionSecret || (!pool && !store)) throw new Error("Production auth is incomplete");
  const client = oidcConfiguration ?? await oidc.discovery(new URL(config.oidcDiscoveryUrl ?? config.oidcIssuer),
    config.oidcClientId, config.oidcClientSecret, undefined, discoveryOptions);
  // An explicit discovery document can live on a different host from its issuer.
  if (config.oidcDiscoveryUrl && client.serverMetadata().issuer !== config.oidcIssuer) {
    throw new Error("OIDC discovery does not match the configured issuer");
  }
  client.timeout = 10;
  oidc.enableNonRepudiationChecks(client);
  const sessionStore = store ?? new (connectPgSimple(session))({ pool, tableName: "web_sessions",
    createTableIfMissing: true, errorLog: () => logger.error("session store operation failed") });
  const middleware = session({ name: COOKIE_NAME, secret: config.sessionSecret, store: sessionStore,
    resave: false, saveUninitialized: false, rolling: true,
    cookie: { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: IDLE_MS } });
  const callbackUrl = `${config.publicOrigin}/auth/callback`;
  return {
    middleware,
    async sessionState(req, res, next) {
      if (req.session.user && req.session.user.expiresAt <= Date.now()) {
        await callSession(req, "destroy");
        res.clearCookie(COOKIE_NAME, { path: "/", secure: true, httpOnly: true, sameSite: "lax" });
        if (req.path === "/auth/session") return res.json({ mode: "production", authenticated: false });
        return res.status(401).json({ error: "Your session expired. Sign in again." });
      }
      next();
    },
    requireUser(req, res, next) {
      if (!req.session?.user) return res.status(401).json({ error: "Sign in to continue." });
      req.ownerId = req.session.user.owner;
      next();
    },
    csrf(req, res, next) {
      if (["GET", "HEAD", "OPTIONS"].includes(req.method)) return next();
      const supplied = req.get("x-csrf-token");
      const expected = req.session?.csrf;
      if (req.get("origin") !== config.publicOrigin || typeof supplied !== "string" || typeof expected !== "string"
          || Buffer.byteLength(supplied) !== Buffer.byteLength(expected)
          || !timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))) {
        return res.status(403).json({ error: "Refresh this page before trying that change again." });
      }
      next();
    },
    mount(app) {
      app.get("/auth/session", (req, res) => res.json(req.session.user
        ? { mode: "production", authenticated: true, csrfToken: req.session.csrf }
        : { mode: "production", authenticated: false }));
      app.get("/auth/login", async (req, res) => {
        await callSession(req, "regenerate");
        const verifier = oidc.randomPKCECodeVerifier();
        const state = oidc.randomState();
        const nonce = oidc.randomNonce();
        req.session.login = { verifier, state, nonce, expiresAt: Date.now() + LOGIN_MS };
        const url = oidc.buildAuthorizationUrl(client, { redirect_uri: callbackUrl, scope: "openid",
          code_challenge: await oidc.calculatePKCECodeChallenge(verifier), code_challenge_method: "S256", state, nonce });
        await callSession(req, "save");
        res.redirect(302, url.href);
      });
      app.get("/auth/callback", async (req, res) => {
        const login = req.session.login;
        delete req.session.login;
        await callSession(req, "save");
        if (!login || login.expiresAt <= Date.now()) return res.status(400).json({ error: "Sign-in expired. Start again." });
        try {
          const tokens = await oidc.authorizationCodeGrant(client, new URL(req.originalUrl, config.publicOrigin), {
            pkceCodeVerifier: login.verifier, expectedState: login.state, expectedNonce: login.nonce, idTokenExpected: true,
          });
          const claims = tokens.claims();
          if (typeof claims?.sub !== "string" || !claims.sub || claims.iss !== client.serverMetadata().issuer) throw new Error("Invalid identity");
          await callSession(req, "regenerate");
          req.session.user = { owner: ownerKey(claims.iss, claims.sub), expiresAt: Date.now() + ABSOLUTE_MS };
          req.session.csrf = token();
          await callSession(req, "save");
          res.redirect(303, "/");
        } catch {
          logger.warn("sign-in verification failed");
          res.status(401).json({ error: "Sign-in could not be verified. Start again." });
        }
      });
      app.post("/auth/logout", this.requireUser, this.csrf, async (req, res) => {
        await callSession(req, "destroy");
        res.clearCookie(COOKIE_NAME, { path: "/", secure: true, httpOnly: true, sameSite: "lax" });
        res.status(204).end();
      });
    },
  };
}
