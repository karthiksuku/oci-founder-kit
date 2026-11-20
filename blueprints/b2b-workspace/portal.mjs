const element = (id) => document.getElementById(id);
const base = "/api/b2b";
let csrf;
let generation = 0;
let draftOrganization = "";
let selectionVersion = 0;
function message(value) { element("status").textContent = value; }
function clearCode() { element("code").value = ""; element("code-box").hidden = true; }
function selectDraftOrganization(id) {
  if (id === draftOrganization) return;
  draftOrganization = id;
  selectionVersion++;
  element("create-request").reset();
  element("invite").reset();
  clearCode();
}
async function api(path, method = "GET", data) {
  const options = { method, credentials: "same-origin", cache: "no-store", redirect: "error",
    headers: { "content-type": "application/json", "x-csrf-token": csrf || "" } };
  if (data) options.body = JSON.stringify(data);
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Request failed.");
  return body;
}
function run(action) {
  return async (event) => {
    event?.preventDefault();
    try { await action(); } catch (err) { message(err.message); }
  };
}
const org = () => base + "/organizations/" + encodeURIComponent(element("organizations").value);
const fields = (form) => Object.fromEntries(new FormData(element(form)));
function list(id, rows, draw) {
  element(id).replaceChildren(...rows.map(row => {
    const item = document.createElement("li"); draw(item, row); return item;
  }));
}
function action(item, label, f) {
  const button = document.createElement("button");
  button.textContent = label;
  button.addEventListener("click", run(f));
  item.append(" ", button);
}
async function refresh(selected = element("organizations").value) {
  const serial = ++generation;
  element("workspace").hidden = true;
  element("admin").hidden = true;
  selectDraftOrganization(selected);
  clearCode();
  const me = await api(base + "/me");
  if (serial !== generation) return;
  element("recipient").value = me.recipientId;
  element("organizations").replaceChildren(...me.organizations.map(o => new Option(o.name, o.id)));
  const current = me.organizations.find(o => o.id === selected) || me.organizations[0];
  selectDraftOrganization(current?.id || "");
  if (!current) { message("Create an organization or accept an invitation."); return; }
  element("organizations").value = current.id;
  const root = org();
  const requests = await api(root + "/requests");
  const access = current.role === "admin" ? await api(root + "/access") : null;
  if (serial !== generation) return;
  element("org-name").textContent = current.name;
  element("org-id").textContent = current.id;
  list("requests", requests.requests, (item, row) => { item.textContent = row.title; });
  if (access) {
    list("invitations", access.invitations, (item, row) => {
      item.textContent = row.recipient + " · " + row.role + " · expires " + new Date(row.expires_at).toLocaleString();
      action(item, "Revoke invitation", async () => { await api(root + "/invitations/" + row.id, "DELETE"); await refresh(); });
    });
    list("members", access.members, (item, member) => {
      item.textContent = member.user_id + " · " + member.role;
      const url = root + "/members/" + member.user_id;
      const role = member.role === "admin" ? "member" : "admin";
      action(item, "Change to " + role, async () => {
        if (window.confirm("Change this person's role to " + role + "?")) { await api(url, "PATCH", { role }); await refresh(); }
      });
      action(item, "Remove", async () => {
        if (window.confirm("Remove this person from this organization?")) { await api(url, "DELETE"); await refresh(); }
      });
    });
    element("admin").hidden = false;
  }
  element("workspace").hidden = false;
  message("Opened " + current.name + " as " + current.role + ".");
  return true;
}
element("organizations").addEventListener("change", run(() => refresh()));
element("create").addEventListener("submit", run(async () => {
  const version = selectionVersion;
  const added = await api(base + "/organizations", "POST", fields("create"));
  if (version !== selectionVersion) return;
  element("create").reset(); await refresh(added.id);
}));
element("accept").addEventListener("submit", run(async () => {
  const version = selectionVersion;
  const { organization, token } = fields("accept");
  await api(base + "/organizations/" + encodeURIComponent(organization) + "/accept", "POST", { token });
  if (version !== selectionVersion) return;
  element("accept").reset(); await refresh(organization);
}));
element("create-request").addEventListener("submit", run(async () => {
  const version = selectionVersion;
  await api(org() + "/requests", "POST", fields("create-request"));
  if (version !== selectionVersion) return;
  element("create-request").reset(); await refresh();
}));
element("invite").addEventListener("submit", run(async () => {
  const version = selectionVersion;
  const selected = element("organizations").value;
  const invitation = await api(org() + "/invitations", "POST", fields("invite"));
  if (version !== selectionVersion) return;
  element("invite").reset();
  if (!await refresh(selected) || draftOrganization !== selected || element("admin").hidden) return;
  element("code").value = invitation.token; element("code-box").hidden = false;
}));
element("export").addEventListener("click", run(async () => {
  const output = await api(org() + "/export");
  const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = "workspace-" + output.organization + ".json";
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}));
run(async () => {
  const session = await api("/auth/session");
  if (!session.authenticated || !session.csrfToken) throw new Error("Sign in again at /auth/login.");
  csrf = session.csrfToken;
  await refresh();
})();
