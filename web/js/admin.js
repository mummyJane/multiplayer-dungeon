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
