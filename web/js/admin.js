"use strict";

const $ = id => document.getElementById(id);
let adminKey   = "";
let adminToken = localStorage.getItem("admin_token") || "";
let adminRole  = localStorage.getItem("admin_role")  || "";
let adminManagedWorlds = JSON.parse(localStorage.getItem("admin_managed_worlds") || "[]");
let uploadedFile = null;

// ── auth helpers ──────────────────────────────────────────────────────────────

function authHeaders(extra = {}) {
  const h = { ...extra };
  if (adminKey)   h["x-admin-key"]    = adminKey;
  if (adminToken) h["Authorization"]  = `Bearer ${adminToken}`;
  return h;
}

async function onAuthSuccess(role, managedWorlds = []) {
  adminRole = role;
  adminManagedWorlds = managedWorlds;
  const status = $("auth-status");
  status.textContent = `✓ ${role}`;
  status.className = "ok";
  $("auth-logout-btn").classList.remove("hidden");
  // show/hide sections based on role
  $("section-worlds").classList.remove("hidden");
  const isFullAdmin = role === "admin";
  $("section-generate").classList.toggle("hidden", !isFullAdmin);
  $("section-manual").classList.toggle("hidden", !isFullAdmin);
  $("section-accounts").classList.toggle("hidden", !isFullAdmin);
  const badge = $("role-badge");
  badge.textContent = role;
  badge.className = `gm-badge role-${role}`;
  if (isFullAdmin) loadAccounts();
  loadWorlds();
}

// API key login
$("auth-btn").addEventListener("click", async () => {
  adminKey = $("admin-key").value.trim();
  adminToken = "";
  const res = await fetch("/admin/worlds", { headers: authHeaders() });
  if (res.ok) {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_role");
    localStorage.removeItem("admin_managed_worlds");
    onAuthSuccess("admin", []);
  } else {
    $("auth-status").textContent = "✗ wrong key";
    $("auth-status").className = "err";
    adminKey = "";
  }
});
$("admin-key").addEventListener("keydown", e => { if (e.key === "Enter") $("auth-btn").click(); });

// Account login (world_admin / admin)
$("auth-user-btn").addEventListener("click", async () => {
  const u = $("auth-username").value.trim();
  const p = $("auth-password").value;
  if (!u || !p) return;
  const res = await fetch("/admin/auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: u, password: p }),
  });
  const data = await res.json();
  if (!res.ok) {
    $("auth-status").textContent = `✗ ${data.detail || "error"}`;
    $("auth-status").className = "err";
    return;
  }
  adminToken = data.token;
  adminKey = "";
  localStorage.setItem("admin_token", adminToken);
  localStorage.setItem("admin_role", data.role);
  localStorage.setItem("admin_managed_worlds", JSON.stringify(data.managed_worlds || []));
  onAuthSuccess(data.role, data.managed_worlds || []);
});
$("auth-password").addEventListener("keydown", e => { if (e.key === "Enter") $("auth-user-btn").click(); });

// Logout
$("auth-logout-btn").addEventListener("click", async () => {
  await fetch("/admin/logout", { method: "POST", headers: authHeaders() });
  adminToken = ""; adminKey = ""; adminRole = ""; adminManagedWorlds = [];
  localStorage.removeItem("admin_token");
  localStorage.removeItem("admin_role");
  localStorage.removeItem("admin_managed_worlds");
  $("auth-status").textContent = "";
  $("auth-logout-btn").classList.add("hidden");
  ["section-worlds","section-generate","section-manual","section-accounts"].forEach(
    id => $(id).classList.add("hidden")
  );
  $("world-editor").classList.add("hidden");
});

// auto-login on page load if token exists
(async () => {
  if (adminToken) {
    const res = await fetch("/admin/worlds", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    if (res.ok) {
      onAuthSuccess(adminRole || "world_admin", adminManagedWorlds);
    } else {
      localStorage.removeItem("admin_token");
      adminToken = "";
    }
  }
})();

// ── tabs (generate section) ───────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
    btn.classList.add("active");
    $("tab-" + btn.dataset.tab).classList.remove("hidden");
  });
});

// ── world list ────────────────────────────────────────────────────────────────

async function loadWorlds() {
  const res = await fetch("/admin/worlds", { headers: authHeaders() });
  if (!res.ok) return;
  const worlds = await res.json();
  const tbody = $("worlds-tbody");
  if (!worlds.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No worlds yet.</td></tr>';
    return;
  }
  const isFullAdmin = adminRole === "admin";
  tbody.innerHTML = worlds.map(w => `
    <tr>
      <td class="mono">${w.id}</td>
      <td>${w.name}</td>
      <td class="muted">${w.description || "—"}</td>
      <td>${w.players}/${w.max_players}</td>
      <td>
        <div class="row-btns">
          <button onclick="openWorldEditor('${w.id}')">Edit</button>
          <button onclick="reloadScripts('${w.id}')">Reload scripts</button>
          ${isFullAdmin ? `<button onclick="removeWorld('${w.id}')" class="muted">Delete</button>` : ""}
        </div>
      </td>
    </tr>`).join("");
}

async function reloadScripts(id) {
  const res = await fetch(`/admin/worlds/${id}/reload-scripts`, {
    method: "POST", headers: authHeaders()
  });
  alert(res.ok ? "Scripts reloaded." : "Error reloading scripts.");
}

async function removeWorld(id) {
  if (!confirm(`Delete world '${id}'? This cannot be undone.`)) return;
  const res = await fetch(`/admin/worlds/${id}`, {
    method: "DELETE", headers: authHeaders()
  });
  if (res.ok) loadWorlds();
}

// ── generate status helpers ───────────────────────────────────────────────────

function setStatus(text, cls = "working") {
  const el = $("generate-status");
  el.textContent = text;
  el.className = cls;
  el.classList.remove("hidden");
}

function showPreview(data) {
  $("preview-tbody").innerHTML = `
    <tr>
      <td>${data.world_id}</td><td>${data.name}</td>
      <td>${data.rooms ?? "?"}</td><td>${data.npcs ?? "?"}</td><td>${data.items ?? "?"}</td>
    </tr>`;
  $("generate-preview").classList.remove("hidden");
}

function showBuildLog(log) {
  if (!log?.length) return;
  const colours = { SEND:"#7fbf7f",RECV:"#7fbfbf",PARSE:"#bfbf7f",WRITE:"#bfbf7f",
                    LOAD:"#7fbfbf",SEED:"#7fbfbf",START:"#7fbf7f",LIVE:"#7fbf7f",
                    WARN:"#bf9f3f",ERROR:"#bf5f5f",ABORT:"#bf5f5f",REPAIR:"#bfbf7f" };
  const fmt = (lines, el) => {
    el.innerHTML = lines.map(line => {
      const verb = line.split(/\s+/)[0];
      const col  = colours[verb] || "#9a9a9a";
      return `<span style="color:${col}">${esc(line)}</span>`;
    }).join("\n");
    el.scrollTop = el.scrollHeight;
  };
  fmt(log, $("build-log"));
  $("build-log-section").classList.remove("hidden");
}

function clearBuildLog() {
  $("build-log").textContent = "";
  $("build-log-section").classList.add("hidden");
}

const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

// ── paste / generate ──────────────────────────────────────────────────────────

$("generate-btn").addEventListener("click", async () => {
  const text = $("spec-input").value.trim();
  if (!text) { setStatus("Please enter a theme or spec text.", "error"); return; }
  setStatus("Asking Claude… (may take 30–60 s for detailed specs)", "working");
  $("generate-preview").classList.add("hidden");
  clearBuildLog();
  try {
    const res = await fetch("/admin/worlds/generate", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    const detail = data.detail || data;
    if (res.ok) {
      setStatus(`✓ World '${data.name}' created (${data.rooms} rooms, ${data.npcs} NPCs, ${data.items} items)`, "success");
      showPreview(data); showBuildLog(data.build_log); loadWorlds();
    } else {
      const err = typeof detail === "object" ? (detail.error || JSON.stringify(detail)) : String(detail);
      setStatus(`✗ ${err}`, "error");
      showBuildLog(typeof detail === "object" ? detail.build_log : null);
    }
  } catch { setStatus("✗ Request failed.", "error"); }
});

// ── file upload ───────────────────────────────────────────────────────────────

const dropZone  = $("drop-zone");
const fileInput = $("file-input");
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault(); dropZone.classList.remove("drag-over");
  if (e.dataTransfer.files[0]) setUploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files[0]) setUploadFile(fileInput.files[0]); });

function setUploadFile(f) {
  uploadedFile = f;
  $("file-name").textContent = `${f.name}  (${(f.size/1024).toFixed(1)} KB)`;
  $("upload-btn").disabled = false;
}

$("upload-btn").addEventListener("click", async () => {
  if (!uploadedFile) return;
  setStatus(`Reading ${uploadedFile.name}…`, "working");
  $("generate-preview").classList.add("hidden");
  clearBuildLog();
  const form = new FormData();
  form.append("file", uploadedFile);
  try {
    const res = await fetch("/admin/worlds/upload", {
      method: "POST", headers: authHeaders(), body: form,
    });
    const data = await res.json();
    const detail = data.detail || data;
    if (res.ok) {
      setStatus(`✓ World '${data.name}' created from ${uploadedFile.name}`, "success");
      showPreview(data); showBuildLog(data.build_log); loadWorlds();
      uploadedFile = null; fileInput.value = "";
      $("file-name").textContent = ""; $("upload-btn").disabled = true;
    } else {
      const err = typeof detail === "object" ? (detail.error || JSON.stringify(detail)) : String(detail);
      setStatus(`✗ ${err}`, "error");
      showBuildLog(typeof detail === "object" ? detail.build_log : null);
    }
  } catch { setStatus("✗ Upload failed.", "error"); }
});

// ── world editor ─────────────────────────────────────────────────────────────

let editorWorldId  = null;
let editorDetail   = null;
let editorScripts  = { rules: "", routines: "", workflows: "" };
let editorActiveScat = "rules";
let crudMode = null;   // { entity: "room"|"npc"|"item", action: "add"|"edit", id: null|str }

// editor tab switching
document.querySelectorAll(".etab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".etab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".etab-panel").forEach(p => p.classList.add("hidden"));
    btn.classList.add("active");
    $("etab-" + btn.dataset.etab).classList.remove("hidden");
    if (btn.dataset.etab === "players" && editorWorldId) loadPlayers(editorWorldId);
  });
});

// script category switching
document.querySelectorAll(".scat").forEach(btn => {
  btn.addEventListener("click", () => {
    editorScripts[editorActiveScat] = $("script-editor").value;
    document.querySelectorAll(".scat").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    editorActiveScat = btn.dataset.scat;
    $("script-editor").value = editorScripts[editorActiveScat];
    $("ed-scripts-status").textContent = "";
  });
});

$("script-editor").addEventListener("keydown", e => {
  if (e.key === "Tab") {
    e.preventDefault();
    const ta = $("script-editor"), s = ta.selectionStart, en = ta.selectionEnd;
    ta.value = ta.value.substring(0, s) + "    " + ta.value.substring(en);
    ta.selectionStart = ta.selectionEnd = s + 4;
  }
});

const creatorBadge = c => c ? `<span class="gm-badge creator-${c.replace(/[^a-z_]/g,'_')}">${c==="claude_api"?"claude":c.startsWith("local_llm")?"llm":c}</span>` : "";

async function openWorldEditor(worldId) {
  editorWorldId = worldId;
  $("world-editor").classList.remove("hidden");
  $("editor-title").textContent = `Editing: ${worldId}`;
  $("ed-config-status").textContent = "";
  $("ed-scripts-status").textContent = "";

  document.querySelectorAll(".etab").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".etab-panel").forEach(p => p.classList.add("hidden"));
  document.querySelector(".etab[data-etab='overview']").classList.add("active");
  $("etab-overview").classList.remove("hidden");

  $("ed-refresh-players").onclick = () => loadPlayers(editorWorldId);
  hideAllCrudForms();

  const [detailRes, scriptsRes] = await Promise.all([
    fetch(`/admin/worlds/${worldId}/detail`, { headers: authHeaders() }),
    fetch(`/admin/worlds/${worldId}/scripts`, { headers: authHeaders() }),
  ]);
  if (!detailRes.ok) { alert("Failed to load world data."); return; }
  editorDetail  = await detailRes.json();
  const scripts = scriptsRes.ok ? await scriptsRes.json() : {};

  $("ed-name").value       = editorDetail.config.name;
  $("ed-desc").value       = editorDetail.config.description;
  $("ed-model").value      = editorDetail.config.ollama_model;
  $("ed-maxplayers").value = editorDetail.config.max_players;

  renderRoomsTable(editorDetail.rooms);
  renderNpcsTable(editorDetail.npcs);
  renderItemsTable(editorDetail.items);

  editorScripts    = { rules: scripts.rules||"", routines: scripts.routines||"", workflows: scripts.workflows||"" };
  editorActiveScat = "rules";
  document.querySelectorAll(".scat").forEach(b => b.classList.remove("active"));
  document.querySelector(".scat[data-scat='rules']").classList.add("active");
  $("script-editor").value = editorScripts.rules;

  $("world-editor").scrollIntoView({ behavior: "smooth" });
}

// ── rooms table & CRUD ────────────────────────────────────────────────────────

function renderRoomsTable(rooms) {
  $("ed-rooms-count").textContent = `${rooms.length} rooms`;
  $("ed-rooms-table").querySelector("tbody").innerHTML = rooms.map(r => {
    const exits = Object.entries(r.exits).map(([d,t]) => `${d}→${t}`).join(", ") || "—";
    const rtype = r.properties?.room_type || "—";
    return `<tr>
      <td class="mono">${r.id}</td>
      <td>${r.name}${creatorBadge(r.creator)}</td>
      <td class="center">${r.z}</td>
      <td class="muted">${r.zone_id}</td>
      <td class="muted">${rtype}</td>
      <td class="muted small">${exits}</td>
      <td>${creatorBadge(r.creator)}</td>
      <td><div class="row-btns">
        <button onclick="editRoom(${JSON.stringify(r.id)})">Edit</button>
        <button onclick="delRoom(${JSON.stringify(r.id)})" class="muted">Del</button>
      </div></td>
    </tr>`;
  }).join("");
}

$("ed-add-room-btn").addEventListener("click", () => showRoomForm(null));

function showRoomForm(r) {
  hideAllCrudForms();
  crudMode = { entity: "room", action: r ? "edit" : "add", id: r?.id || null };
  $("rf-id").value    = r?.id    || "";
  $("rf-id").disabled = !!r;
  $("rf-name").value  = r?.name  || "";
  $("rf-zone").value  = r?.zone_id || "default";
  $("rf-z").value     = r?.z ?? 0;
  $("rf-desc").value  = r?.description || "";
  $("rf-exits").value = r ? JSON.stringify(r.exits || {}) : "{}";
  $("rf-props").value = r ? JSON.stringify(r.properties || {}) : "{}";
  $("rf-status").textContent = "";
  $("room-form").classList.remove("hidden");
  $("rf-name").focus();
}

function editRoom(id) {
  const r = editorDetail.rooms.find(x => x.id === id);
  if (r) showRoomForm(r);
}

async function delRoom(id) {
  if (!confirm(`Delete room '${id}'?`)) return;
  const res = await fetch(`/admin/worlds/${editorWorldId}/rooms/${id}`, {
    method: "DELETE", headers: authHeaders()
  });
  if (res.ok) refreshDetail();
  else alert("Delete failed: " + (await res.json()).detail);
}

$("rf-save-btn").addEventListener("click", async () => {
  const id = $("rf-id").value.trim();
  if (!id) { $("rf-status").textContent = "ID required"; return; }
  let exits = {}, props = {};
  try { exits = JSON.parse($("rf-exits").value || "{}"); } catch { $("rf-status").textContent = "Invalid exits JSON"; return; }
  try { props = JSON.parse($("rf-props").value || "{}"); } catch { $("rf-status").textContent = "Invalid properties JSON"; return; }
  const body = { id, name: $("rf-name").value, description: $("rf-desc").value,
                 zone_id: $("rf-zone").value||"default", z: parseInt($("rf-z").value)||0,
                 exits, properties: props };
  const isAdd = crudMode?.action === "add";
  const url   = isAdd ? `/admin/worlds/${editorWorldId}/rooms` : `/admin/worlds/${editorWorldId}/rooms/${id}`;
  const res   = await fetch(url, {
    method: isAdd ? "POST" : "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (res.ok) { hideAllCrudForms(); refreshDetail(); }
  else $("rf-status").textContent = "✗ " + ((await res.json()).detail || "Error");
});
$("rf-cancel-btn").addEventListener("click", hideAllCrudForms);

// ── NPCs table & CRUD ─────────────────────────────────────────────────────────

function renderNpcsTable(npcs) {
  $("ed-npcs-count").textContent = `${npcs.length} NPCs`;
  $("ed-npcs-table").querySelector("tbody").innerHTML = npcs.map(n => {
    const role = n.properties?.role || "—";
    return `<tr>
      <td class="mono">${n.id}</td>
      <td>${n.name}${creatorBadge(n.creator)}</td>
      <td class="muted small">${n.description}</td>
      <td class="mono muted">${n.room_id}</td>
      <td class="muted">${role}</td>
      <td>${creatorBadge(n.creator)}</td>
      <td><div class="row-btns">
        <button onclick="editNpc(${JSON.stringify(n.id)})">Edit</button>
        <button onclick="delNpc(${JSON.stringify(n.id)})" class="muted">Del</button>
      </div></td>
    </tr>`;
  }).join("");
}

$("ed-add-npc-btn").addEventListener("click", () => showNpcForm(null));

function showNpcForm(n) {
  hideAllCrudForms();
  crudMode = { entity: "npc", action: n ? "edit" : "add", id: n?.id || null };
  $("nf-id").value       = n?.id          || "";
  $("nf-id").disabled    = !!n;
  $("nf-name").value     = n?.name        || "";
  $("nf-room").value     = n?.room_id     || "";
  $("nf-desc").value     = n?.description || "";
  $("nf-dialogue").value = (n?.dialogue || []).join("\n");
  $("nf-status").textContent = "";
  $("npc-form").classList.remove("hidden");
  $("nf-name").focus();
}

function editNpc(id) {
  const n = editorDetail.npcs.find(x => x.id === id);
  if (n) showNpcForm(n);
}

async function delNpc(id) {
  if (!confirm(`Delete NPC '${id}'?`)) return;
  const res = await fetch(`/admin/worlds/${editorWorldId}/npcs/${id}`, {
    method: "DELETE", headers: authHeaders()
  });
  if (res.ok) refreshDetail();
  else alert("Delete failed: " + (await res.json()).detail);
}

$("nf-save-btn").addEventListener("click", async () => {
  const id = $("nf-id").value.trim();
  if (!id) { $("nf-status").textContent = "ID required"; return; }
  const dialogue = $("nf-dialogue").value.split("\n").map(l => l.trim()).filter(Boolean);
  const body = { id, name: $("nf-name").value, description: $("nf-desc").value,
                 room_id: $("nf-room").value, dialogue };
  const isAdd = crudMode?.action === "add";
  const url   = isAdd ? `/admin/worlds/${editorWorldId}/npcs` : `/admin/worlds/${editorWorldId}/npcs/${id}`;
  const res   = await fetch(url, {
    method: isAdd ? "POST" : "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (res.ok) { hideAllCrudForms(); refreshDetail(); }
  else $("nf-status").textContent = "✗ " + ((await res.json()).detail || "Error");
});
$("nf-cancel-btn").addEventListener("click", hideAllCrudForms);

// ── items table & CRUD ────────────────────────────────────────────────────────

function renderItemsTable(items) {
  $("ed-items-count").textContent = `${items.length} items`;
  $("ed-items-table").querySelector("tbody").innerHTML = items.map(i => {
    const props = Object.entries(i.properties||{}).map(([k,v]) => `${k}:${JSON.stringify(v)}`).join(", ") || "—";
    return `<tr>
      <td class="mono">${i.id}</td>
      <td>${i.name}${creatorBadge(i.creator)}</td>
      <td class="muted">${i.item_type}</td>
      <td class="mono muted">${i.room_id}</td>
      <td class="muted small">${props}</td>
      <td>${creatorBadge(i.creator)}</td>
      <td><div class="row-btns">
        <button onclick="editItem(${JSON.stringify(i.id)})">Edit</button>
        <button onclick="delItem(${JSON.stringify(i.id)})" class="muted">Del</button>
      </div></td>
    </tr>`;
  }).join("");
}

$("ed-add-item-btn").addEventListener("click", () => showItemForm(null));

function showItemForm(i) {
  hideAllCrudForms();
  crudMode = { entity: "item", action: i ? "edit" : "add", id: i?.id || null };
  $("if-id").value       = i?.id          || "";
  $("if-id").disabled    = !!i;
  $("if-name").value     = i?.name        || "";
  $("if-room").value     = i?.room_id     || "";
  $("if-desc").value     = i?.description || "";
  $("if-type").value     = i?.item_type   || "misc";
  $("if-props").value    = JSON.stringify(i?.properties || {});
  $("if-status").textContent = "";
  $("item-form").classList.remove("hidden");
  $("if-name").focus();
}

function editItem(id) {
  const i = editorDetail.items.find(x => x.id === id);
  if (i) showItemForm(i);
}

async function delItem(id) {
  if (!confirm(`Delete item '${id}'?`)) return;
  const res = await fetch(`/admin/worlds/${editorWorldId}/items/${id}`, {
    method: "DELETE", headers: authHeaders()
  });
  if (res.ok) refreshDetail();
  else alert("Delete failed: " + (await res.json()).detail);
}

$("if-save-btn").addEventListener("click", async () => {
  const id = $("if-id").value.trim();
  if (!id) { $("if-status").textContent = "ID required"; return; }
  let props = {};
  try { props = JSON.parse($("if-props").value || "{}"); } catch { $("if-status").textContent = "Invalid properties JSON"; return; }
  const body = { id, name: $("if-name").value, description: $("if-desc").value,
                 item_type: $("if-type").value, room_id: $("if-room").value||null,
                 properties: props };
  const isAdd = crudMode?.action === "add";
  const url   = isAdd ? `/admin/worlds/${editorWorldId}/items` : `/admin/worlds/${editorWorldId}/items/${id}`;
  const res   = await fetch(url, {
    method: isAdd ? "POST" : "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (res.ok) { hideAllCrudForms(); refreshDetail(); }
  else $("if-status").textContent = "✗ " + ((await res.json()).detail || "Error");
});
$("if-cancel-btn").addEventListener("click", hideAllCrudForms);

// ── CRUD helpers ──────────────────────────────────────────────────────────────

function hideAllCrudForms() {
  ["room-form","npc-form","item-form"].forEach(id => $(id).classList.add("hidden"));
  crudMode = null;
}

async function refreshDetail() {
  const res = await fetch(`/admin/worlds/${editorWorldId}/detail`, { headers: authHeaders() });
  if (!res.ok) return;
  editorDetail = await res.json();
  renderRoomsTable(editorDetail.rooms);
  renderNpcsTable(editorDetail.npcs);
  renderItemsTable(editorDetail.items);
}

// ── players ───────────────────────────────────────────────────────────────────

async function loadPlayers(worldId) {
  const res = await fetch(`/admin/worlds/${worldId}/players`, { headers: authHeaders() });
  if (!res.ok) return;
  const players = await res.json();
  const count = $("ed-players-count");
  const tbody = $("ed-players-table").querySelector("tbody");
  count.textContent = `${players.length} active player${players.length !== 1 ? "s" : ""}`;
  if (!players.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No players online.</td></tr>';
    return;
  }
  tbody.innerHTML = players.map(p => {
    const worn  = Object.entries(p.worn||{}).map(([s,n]) => `${s}: ${n}`).join(", ") || "—";
    const efx   = (p.effects||[]).join(", ") || "—";
    const flags = Object.entries(p.flags||{})
      .filter(([,v]) => v !== false && v !== null && v !== 0 && v !== "")
      .map(([k,v]) => v===true ? k : `${k}:${v}`).join(", ") || "—";
    return `<tr>
      <td><strong>${p.name}</strong></td>
      <td class="muted">${p.username}</td>
      <td class="mono muted">${p.room_name}</td>
      <td>${p.hp}/${p.max_hp}</td>
      <td class="small muted">${worn}</td>
      <td class="small muted">${efx}</td>
      <td class="small muted">${flags}</td>
    </tr>`;
  }).join("");
}

// ── config / scripts ──────────────────────────────────────────────────────────

$("ed-close").addEventListener("click", () => {
  $("world-editor").classList.add("hidden");
  editorWorldId = null; editorDetail = null;
});

$("ed-save-config").addEventListener("click", async () => {
  if (!editorWorldId) return;
  const body = { name: $("ed-name").value.trim(), description: $("ed-desc").value.trim(),
                 ollama_model: $("ed-model").value.trim(),
                 max_players: parseInt($("ed-maxplayers").value, 10) || 0 };
  const res  = await fetch(`/admin/worlds/${editorWorldId}/config`, {
    method: "PATCH", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  const el = $("ed-config-status");
  if (res.ok) { el.textContent = `✓ Saved (${data.name})`; el.className = "ok"; loadWorlds(); }
  else { el.textContent = `✗ ${data.detail || "Error"}`; el.className = "err"; }
});

$("ed-save-scripts").addEventListener("click", async () => {
  if (!editorWorldId) return;
  editorScripts[editorActiveScat] = $("script-editor").value;
  const res = await fetch(`/admin/worlds/${editorWorldId}/scripts`, {
    method: "PUT", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(editorScripts),
  });
  const data = await res.json();
  const el = $("ed-scripts-status");
  if (res.ok) {
    const errs = data.errors?.length ? `  ⚠ ${data.errors.join("; ")}` : "";
    el.textContent = `✓ Saved ${data.saved.join(", ")} — scripts reloaded${errs}`;
    el.className = data.errors?.length ? "warn" : "ok";
  } else { el.textContent = `✗ ${data.detail || "Error"}`; el.className = "err"; }
});

// ── expand tab ────────────────────────────────────────────────────────────────

$("expand-btn").addEventListener("click", async () => {
  const text = $("expand-spec").value.trim();
  if (!text || !editorWorldId) return;
  $("expand-status").textContent = "Asking Claude…";
  $("expand-log-section").classList.add("hidden");
  try {
    const res = await fetch(`/admin/worlds/${editorWorldId}/expand`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    const detail = data.detail || data;
    if (res.ok) {
      $("expand-status").textContent = `✓ +${data.rooms} rooms, +${data.npcs} NPCs, +${data.items} items`;
      showExpandLog(detail.build_log || []);
      refreshDetail();
    } else {
      $("expand-status").textContent = `✗ ${typeof detail === "object" ? (detail.error || JSON.stringify(detail)) : detail}`;
      showExpandLog(typeof detail === "object" ? detail.build_log : []);
    }
  } catch { $("expand-status").textContent = "✗ Request failed."; }
});

function showExpandLog(log) {
  if (!log?.length) return;
  const colours = { SEND:"#7fbf7f",RECV:"#7fbfbf",PARSE:"#bfbf7f",LIVE:"#7fbf7f",
                    LOAD:"#7fbfbf",WARN:"#bf9f3f",ERROR:"#bf5f5f",ABORT:"#bf5f5f",REPAIR:"#bfbf7f" };
  $("expand-log").innerHTML = log.map(line => {
    const verb = line.split(/\s+/)[0];
    const col  = colours[verb] || "#9a9a9a";
    return `<span style="color:${col}">${esc(line)}</span>`;
  }).join("\n");
  $("expand-log-section").classList.remove("hidden");
  $("expand-log").scrollTop = $("expand-log").scrollHeight;
}

// ── manual create ─────────────────────────────────────────────────────────────

$("manual-btn").addEventListener("click", async () => {
  const id   = $("manual-id").value.trim();
  const name = $("manual-name").value.trim();
  if (!id || !name) return;
  const res = await fetch("/admin/worlds/manual", {
    method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ id, name }),
  });
  const data = await res.json();
  const el = $("manual-status");
  if (res.ok) {
    el.textContent = `✓ '${data.name}' created`; el.style.color = "var(--accent)";
    $("manual-id").value = ""; $("manual-name").value = ""; loadWorlds();
  } else { el.textContent = `✗ ${data.detail || "Error"}`; el.style.color = "var(--error)"; }
});

// ── accounts (full admin) ─────────────────────────────────────────────────────

let accountEditTarget = null;

async function loadAccounts() {
  const res = await fetch("/admin/accounts", { headers: authHeaders() });
  if (!res.ok) return;
  const accounts = await res.json();
  $("accounts-tbody").innerHTML = accounts.map(a => `
    <tr>
      <td><strong>${a.username}</strong></td>
      <td><span class="role-chip role-${a.role}">${a.role}</span></td>
      <td class="muted small">${(a.managed_worlds||[]).join(", ") || "—"}</td>
      <td class="muted small">${a.last_login ? a.last_login.replace("T"," ").replace("Z","") : "—"}</td>
      <td><button onclick="startEditAccount(${JSON.stringify(a.username)},${JSON.stringify(a.role)},${JSON.stringify((a.managed_worlds||[]).join(","))})">Edit role</button></td>
    </tr>`).join("");
}

function startEditAccount(username, role, managedWorldsStr) {
  accountEditTarget = username;
  $("ae-username").textContent = username;
  $("ae-role").value   = role;
  $("ae-worlds").value = managedWorldsStr;
  $("ae-status").textContent = "";
  $("account-edit").classList.remove("hidden");
  $("ae-role").focus();
}

$("ae-save-btn").addEventListener("click", async () => {
  if (!accountEditTarget) return;
  const role   = $("ae-role").value;
  const worlds = $("ae-worlds").value.split(",").map(s => s.trim()).filter(Boolean);
  const res = await fetch(`/admin/accounts/${accountEditTarget}/role`, {
    method: "PATCH", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ role, managed_worlds: worlds }),
  });
  const data = await res.json();
  const el = $("ae-status");
  if (res.ok) {
    el.textContent = `✓ ${accountEditTarget} → ${data.role}`; el.className = "ok";
    $("account-edit").classList.add("hidden");
    loadAccounts();
  } else { el.textContent = `✗ ${data.detail || "Error"}`; el.className = "err"; }
});

$("ae-cancel-btn").addEventListener("click", () => {
  $("account-edit").classList.add("hidden");
  accountEditTarget = null;
});
