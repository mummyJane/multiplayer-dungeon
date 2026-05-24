"use strict";

const $ = id => document.getElementById(id);
let adminKey = "";
let uploadedFile = null;

// ── auth ──────────────────────────────────────────────────────────────────────

function authHeaders(extra = {}) {
  return { "x-admin-key": adminKey, ...extra };
}

$("auth-btn").addEventListener("click", async () => {
  adminKey = $("admin-key").value.trim();
  const res = await fetch("/admin/worlds", { headers: authHeaders() });
  const status = $("auth-status");
  if (res.ok) {
    status.textContent = "✓ authenticated";
    status.className = "ok";
    loadWorlds();
  } else {
    status.textContent = "✗ wrong key";
    status.className = "err";
    adminKey = "";
  }
});

$("admin-key").addEventListener("keydown", e => { if (e.key === "Enter") $("auth-btn").click(); });

// ── tabs ──────────────────────────────────────────────────────────────────────

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
  tbody.innerHTML = worlds.map(w => `
    <tr>
      <td>${w.id}</td>
      <td>${w.name}</td>
      <td class="muted">${w.description || "—"}</td>
      <td>${w.players}/${w.max_players}</td>
      <td>
        <button onclick="openWorldEditor('${w.id}')">Edit</button>
        <button onclick="reloadScripts('${w.id}')">Reload scripts</button>
        <button onclick="removeWorld('${w.id}')" class="muted">Delete</button>
      </td>
    </tr>`).join("");
}

async function reloadScripts(id) {
  const res = await fetch(`/admin/worlds/${id}/reload-scripts`, {
    method: "POST", headers: authHeaders()
  });
  setStatus(res.ok ? "Scripts reloaded." : "Error.", res.ok ? "success" : "error");
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
      <td>${data.world_id}</td>
      <td>${data.name}</td>
      <td>${data.rooms ?? "?"}</td>
      <td>${data.npcs ?? "?"}</td>
      <td>${data.items ?? "?"}</td>
    </tr>`;
  $("generate-preview").classList.remove("hidden");
}

function showBuildLog(log) {
  if (!log || !log.length) return;
  const colours = { SEND: "#7fbf7f", RECV: "#7fbfbf", PARSE: "#bfbf7f",
                    WRITE: "#bfbf7f", LOAD: "#7fbfbf", SEED: "#7fbfbf",
                    START: "#7fbf7f", WARN: "#bf9f3f", ERROR: "#bf5f5f",
                    ABORT: "#bf5f5f" };
  $("build-log").innerHTML = log.map(line => {
    const verb = line.split(/\s+/)[0];
    const col = colours[verb] || "#9a9a9a";
    const safe = line.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    return `<span style="color:${col}">${safe}</span>`;
  }).join("\n");
  $("build-log-section").classList.remove("hidden");
  $("build-log").scrollTop = $("build-log").scrollHeight;
}

function clearBuildLog() {
  $("build-log").textContent = "";
  $("build-log-section").classList.add("hidden");
}

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
      showPreview(data);
      showBuildLog(data.build_log);
      loadWorlds();
    } else {
      const err = typeof detail === "object" ? (detail.error || JSON.stringify(detail)) : String(detail);
      setStatus(`✗ ${err}`, "error");
      showBuildLog(typeof detail === "object" ? detail.build_log : null);
    }
  } catch (e) {
    setStatus("✗ Request failed — is the server running?", "error");
  }
});

// ── file upload ───────────────────────────────────────────────────────────────

const dropZone  = $("drop-zone");
const fileInput = $("file-input");

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const f = e.dataTransfer.files[0];
  if (f) setUploadFile(f);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) setUploadFile(fileInput.files[0]);
});

function setUploadFile(f) {
  uploadedFile = f;
  $("file-name").textContent = `${f.name}  (${(f.size / 1024).toFixed(1)} KB)`;
  $("upload-btn").disabled = false;
}

$("upload-btn").addEventListener("click", async () => {
  if (!uploadedFile) return;

  setStatus(`Reading ${uploadedFile.name}…`, "working");
  $("generate-preview").classList.add("hidden");

  const form = new FormData();
  form.append("file", uploadedFile);

  clearBuildLog();
  try {
    const res = await fetch("/admin/worlds/upload", {
      method: "POST",
      headers: authHeaders(),   // no Content-Type — browser sets multipart boundary
      body: form,
    });
    const data = await res.json();
    const detail = data.detail || data;
    if (res.ok) {
      setStatus(`✓ World '${data.name}' created from ${uploadedFile.name} (${data.rooms} rooms, ${data.npcs} NPCs, ${data.items} items)`, "success");
      showPreview(data);
      showBuildLog(data.build_log);
      loadWorlds();
      // reset
      uploadedFile = null;
      fileInput.value = "";
      $("file-name").textContent = "";
      $("upload-btn").disabled = true;
    } else {
      const err = typeof detail === "object" ? (detail.error || JSON.stringify(detail)) : String(detail);
      setStatus(`✗ ${err}`, "error");
      showBuildLog(typeof detail === "object" ? detail.build_log : null);
    }
  } catch (e) {
    setStatus("✗ Upload failed.", "error");
  }
});

// ── world editor ─────────────────────────────────────────────────────────────

let editorWorldId = null;
let editorScripts = { rules: "", routines: "", workflows: "" };
let editorActiveScat = "rules";

// editor tab switching
document.querySelectorAll(".etab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".etab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".etab-panel").forEach(p => p.classList.add("hidden"));
    btn.classList.add("active");
    $("etab-" + btn.dataset.etab).classList.remove("hidden");
  });
});

// script category switching
document.querySelectorAll(".scat").forEach(btn => {
  btn.addEventListener("click", () => {
    // save current textarea content before switching
    editorScripts[editorActiveScat] = $("script-editor").value;
    document.querySelectorAll(".scat").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    editorActiveScat = btn.dataset.scat;
    $("script-editor").value = editorScripts[editorActiveScat];
    $("ed-scripts-status").textContent = "";
  });
});

// Tab key inserts spaces in the script editor
$("script-editor").addEventListener("keydown", e => {
  if (e.key === "Tab") {
    e.preventDefault();
    const ta = $("script-editor");
    const s = ta.selectionStart, en = ta.selectionEnd;
    ta.value = ta.value.substring(0, s) + "    " + ta.value.substring(en);
    ta.selectionStart = ta.selectionEnd = s + 4;
  }
});

async function openWorldEditor(worldId) {
  editorWorldId = worldId;
  $("world-editor").classList.remove("hidden");
  $("editor-title").textContent = `Editing: ${worldId}`;
  $("ed-config-status").textContent = "";
  $("ed-scripts-status").textContent = "";

  // reset to overview tab
  document.querySelectorAll(".etab").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".etab-panel").forEach(p => p.classList.add("hidden"));
  document.querySelector(".etab[data-etab='overview']").classList.add("active");
  $("etab-overview").classList.remove("hidden");

  // load detail + scripts in parallel
  const [detailRes, scriptsRes] = await Promise.all([
    fetch(`/admin/worlds/${worldId}/detail`, { headers: authHeaders() }),
    fetch(`/admin/worlds/${worldId}/scripts`, { headers: authHeaders() }),
  ]);

  if (!detailRes.ok || !scriptsRes.ok) {
    alert("Failed to load world data.");
    return;
  }
  const detail  = await detailRes.json();
  const scripts = await scriptsRes.json();

  // populate config
  $("ed-name").value       = detail.config.name;
  $("ed-desc").value       = detail.config.description;
  $("ed-model").value      = detail.config.ollama_model;
  $("ed-maxplayers").value = detail.config.max_players;

  // populate rooms table
  $("ed-rooms-count").textContent = `${detail.rooms.length} rooms`;
  $("ed-rooms-table").querySelector("tbody").innerHTML = detail.rooms.map(r => {
    const exits = Object.entries(r.exits).map(([d,t]) => `${d}→${t}`).join(", ") || "—";
    const rtype = r.properties?.room_type || "—";
    return `<tr>
      <td class="mono">${r.id}</td>
      <td>${r.name}</td>
      <td class="center">${r.z}</td>
      <td class="muted">${r.zone_id}</td>
      <td class="muted">${rtype}</td>
      <td class="muted small">${exits}</td>
    </tr>`;
  }).join("");

  // populate npcs table
  $("ed-npcs-count").textContent = `${detail.npcs.length} NPCs`;
  $("ed-npcs-table").querySelector("tbody").innerHTML = detail.npcs.map(n => {
    const role  = n.properties?.role  || "—";
    const shift = n.properties?.shift
      ? `${n.properties.shift} ${n.properties.shift_start||""}–${n.properties.shift_end||""}`
      : "—";
    return `<tr>
      <td class="mono">${n.id}</td>
      <td>${n.name}</td>
      <td class="muted small">${n.description}</td>
      <td class="mono muted">${n.room_id}</td>
      <td class="muted">${role}</td>
      <td class="muted">${shift}</td>
    </tr>`;
  }).join("");

  // load scripts into editor state
  editorScripts   = { rules: scripts.rules || "", routines: scripts.routines || "", workflows: scripts.workflows || "" };
  editorActiveScat = "rules";
  document.querySelectorAll(".scat").forEach(b => b.classList.remove("active"));
  document.querySelector(".scat[data-scat='rules']").classList.add("active");
  $("script-editor").value = editorScripts.rules;

  $("world-editor").scrollIntoView({ behavior: "smooth" });
}

$("ed-close").addEventListener("click", () => {
  $("world-editor").classList.add("hidden");
  editorWorldId = null;
});

$("ed-save-config").addEventListener("click", async () => {
  if (!editorWorldId) return;
  const body = {
    name:        $("ed-name").value.trim(),
    description: $("ed-desc").value.trim(),
    ollama_model:$("ed-model").value.trim(),
    max_players: parseInt($("ed-maxplayers").value, 10) || 0,
  };
  const res  = await fetch(`/admin/worlds/${editorWorldId}/config`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  const el = $("ed-config-status");
  if (res.ok) {
    el.textContent = `✓ Saved (${data.name})`;
    el.className = "ok";
    loadWorlds();
  } else {
    el.textContent = `✗ ${data.detail || "Error"}`;
    el.className = "err";
  }
});

$("ed-save-scripts").addEventListener("click", async () => {
  if (!editorWorldId) return;
  // capture current textarea before sending
  editorScripts[editorActiveScat] = $("script-editor").value;

  const res = await fetch(`/admin/worlds/${editorWorldId}/scripts`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(editorScripts),
  });
  const data = await res.json();
  const el = $("ed-scripts-status");
  if (res.ok) {
    const errs = data.errors?.length ? `  ⚠ ${data.errors.join("; ")}` : "";
    el.textContent = `✓ Saved ${data.saved.join(", ")} — scripts reloaded${errs}`;
    el.className = data.errors?.length ? "warn" : "ok";
  } else {
    el.textContent = `✗ ${data.detail || "Error"}`;
    el.className = "err";
  }
});

// ── manual create ─────────────────────────────────────────────────────────────

$("manual-btn").addEventListener("click", async () => {
  const id   = $("manual-id").value.trim();
  const name = $("manual-name").value.trim();
  if (!id || !name) return;

  const res = await fetch("/admin/worlds/manual", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ id, name }),
  });
  const data = await res.json();
  const el = $("manual-status");
  if (res.ok) {
    el.textContent = `✓ '${data.name}' created`;
    el.style.color = "var(--accent)";
    $("manual-id").value = "";
    $("manual-name").value = "";
    loadWorlds();
  } else {
    el.textContent = `✗ ${data.detail || "Error"}`;
    el.style.color = "var(--error)";
  }
});
