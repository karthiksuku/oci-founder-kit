// Taskboard browser client: tasks, done toggles and direct-to-bucket uploads.

const els = {
  form: document.getElementById("new-task"),
  title: document.getElementById("title"),
  list: document.getElementById("tasks"),
  empty: document.getElementById("empty"),
  status: document.getElementById("status"),
  health: document.getElementById("health"),
};

function say(message) {
  els.status.textContent = message;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: options.body ? { "content-type": "application/json" } : undefined,
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}

function el(tag, attrs = {}, text = "") {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text) node.textContent = text;
  return node;
}

async function uploadFile(task, file) {
  say(`Uploading ${file.name}…`);
  const { objectName, uploadUrl } = await api(`/api/tasks/${task.id}/attachments/upload-url`, {
    method: "POST", body: JSON.stringify({ filename: file.name, size: file.size, contentType: file.type }),
  });
  const put = await fetch(uploadUrl, { method: "PUT", body: file });
  if (!put.ok) throw new Error(`Upload to storage failed (${put.status})`);
  await api(`/api/tasks/${task.id}/attachments`, {
    method: "POST", body: JSON.stringify({ objectName, filename: file.name, size: file.size }),
  });
  say(`Uploaded ${file.name}.`);
}

function renderTask(task, attachments) {
  const item = el("li", { class: `task${task.done ? " done" : ""}` });
  const row = el("div", { class: "task-row" });
  const box = el("input", { type: "checkbox", "aria-label": `Mark "${task.title}" done` });
  box.checked = task.done;
  box.addEventListener("change", () => act(() => api(`/api/tasks/${task.id}`, {
    method: "PATCH", body: JSON.stringify({ done: box.checked }),
  })));
  const remove = el("button", { type: "button", class: "link danger" }, "Delete");
  remove.addEventListener("click", () => act(() => api(`/api/tasks/${task.id}`, { method: "DELETE" })));
  row.append(box, el("span", { class: "title" }, task.title), remove);
  item.append(row);

  const files = el("div", { class: "files" });
  attachments.forEach((a) => files.append(el("a", { href: `/api/attachments/${a.id}/download` }, a.filename)));
  const label = el("label", { class: "upload" }, "Attach a file ");
  const picker = el("input", { type: "file" });
  picker.addEventListener("change", () => {
    if (picker.files[0]) act(() => uploadFile(task, picker.files[0]));
  });
  label.append(picker);
  item.append(files, label);
  return item;
}

async function refresh() {
  const tasks = await api("/api/tasks");
  const detailed = await Promise.all(tasks.map((t) => api(`/api/tasks/${t.id}`)));
  els.list.replaceChildren(...detailed.map((t) => renderTask(t, t.attachments || [])));
  els.empty.hidden = tasks.length > 0;
}

async function act(fn) {
  try {
    await fn();
    await refresh();
  } catch (err) {
    say(err.message);
  }
}

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const title = els.title.value.trim();
  if (!title) return;
  act(async () => {
    await api("/api/tasks", { method: "POST", body: JSON.stringify({ title }) });
    els.title.value = "";
    say("");
  });
});

async function checkHealth() {
  try {
    const res = await fetch("/readyz");
    els.health.textContent = res.ok ? "Database connected." : "Database unavailable.";
  } catch {
    els.health.textContent = "Cannot reach the API.";
  }
}

act(async () => {});
checkHealth();
