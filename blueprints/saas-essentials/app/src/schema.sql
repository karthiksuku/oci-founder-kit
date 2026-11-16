-- Apply with the reviewed migration identity; use separate web/worker DB roles in OCI.
CREATE TABLE IF NOT EXISTS saas_ownership (
 environment TEXT PRIMARY KEY,
 owner TEXT NOT NULL CHECK(owner IN ('source','paused','oci')),
 generation BIGINT NOT NULL DEFAULT 1,
 evidence_sha256 TEXT NOT NULL CHECK(evidence_sha256 ~ '^[0-9a-f]{64}$'),
 -- PostgreSQL row-lock permission without authority to edit ownership/audit data.
 lock_guard BOOLEAN NOT NULL DEFAULT FALSE CHECK(lock_guard = FALSE)
);
CREATE TABLE IF NOT EXISTS saas_jobs (
 id UUID PRIMARY KEY,
 environment TEXT NOT NULL REFERENCES saas_ownership(environment),
 owner_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('request','webhook','summary')),
 payload JSONB NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','running','done','dead')),
 attempts INTEGER NOT NULL DEFAULT 0,
 replay_count INTEGER NOT NULL DEFAULT 0,
 lease UUID,
 lease_until TIMESTAMPTZ,
 result JSONB,
 error_code TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS saas_outbox (
 job_id UUID PRIMARY KEY REFERENCES saas_jobs(id),
 published_at TIMESTAMPTZ,
 available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 lease UUID,
 lease_until TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS saas_inbox (
 environment TEXT NOT NULL,
 event_id TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL,
 job_id UUID NOT NULL REFERENCES saas_jobs(id),
 PRIMARY KEY(environment,event_id)
);
CREATE TABLE IF NOT EXISTS saas_external_requests (
 environment TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 external_id TEXT NOT NULL,
 version BIGINT NOT NULL,
 task_id BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
 PRIMARY KEY(environment,owner_id,external_id)
);
CREATE TABLE IF NOT EXISTS saas_schedules (
 environment TEXT NOT NULL REFERENCES saas_ownership(environment),
 id TEXT NOT NULL,
 version INTEGER NOT NULL,
 owner_id TEXT NOT NULL,
 period_seconds INTEGER NOT NULL CHECK(period_seconds BETWEEN 3600 AND 2678400),
 anchor TIMESTAMPTZ NOT NULL,
 last_due TIMESTAMPTZ,
 skipped BIGINT NOT NULL DEFAULT 0,
 enabled BOOLEAN NOT NULL DEFAULT FALSE,
 PRIMARY KEY(environment,id)
);
CREATE TABLE IF NOT EXISTS saas_schedule_runs (
 environment TEXT NOT NULL,
 schedule_id TEXT NOT NULL,
 version INTEGER NOT NULL,
 due_at TIMESTAMPTZ NOT NULL,
 job_id UUID NOT NULL REFERENCES saas_jobs(id),
 PRIMARY KEY(environment,schedule_id,version,due_at)
);
CREATE TABLE IF NOT EXISTS saas_replays (
 environment TEXT NOT NULL,
 job_id UUID NOT NULL REFERENCES saas_jobs(id),
 replay_count INTEGER NOT NULL,
 evidence_sha256 TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(environment,job_id,replay_count)
);
CREATE INDEX IF NOT EXISTS saas_outbox_due ON saas_outbox(available_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS saas_jobs_owner ON saas_jobs(environment,owner_id,created_at);
