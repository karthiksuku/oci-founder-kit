-- Run once as the migration owner against the intended database.
BEGIN;
CREATE SCHEMA founder_workspace;
REVOKE ALL ON SCHEMA founder_workspace FROM PUBLIC;

CREATE TABLE founder_workspace.organizations (
  id uuid PRIMARY KEY,
  name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120)
);
CREATE TABLE founder_workspace.memberships (
  organization_id uuid NOT NULL REFERENCES founder_workspace.organizations,
  user_id text NOT NULL CHECK (user_id ~ '^[a-f0-9]{64}$'),
  role text NOT NULL CHECK (role IN ('admin', 'member')),
  PRIMARY KEY (organization_id, user_id)
);
CREATE INDEX workspace_memberships_by_user ON founder_workspace.memberships (user_id, organization_id);
CREATE TABLE founder_workspace.invitations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  issued_by text NOT NULL,
  recipient text NOT NULL CHECK (recipient ~ '^[a-f0-9]{64}$'),
  role text NOT NULL CHECK (role IN ('admin', 'member')),
  token_hash text NOT NULL CHECK (token_hash ~ '^[a-f0-9]{64}$'),
  expires_at timestamptz NOT NULL,
  UNIQUE (organization_id, recipient),
  FOREIGN KEY (organization_id, issued_by)
    REFERENCES founder_workspace.memberships (organization_id, user_id) ON DELETE CASCADE
);
CREATE TABLE founder_workspace.requests (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES founder_workspace.organizations,
  title text NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX workspace_requests_by_organization ON founder_workspace.requests (organization_id, created_at, id);
COMMIT;
