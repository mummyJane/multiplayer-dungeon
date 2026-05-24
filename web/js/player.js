"use strict";

const $ = id => document.getElementById(id);

let _token = localStorage.getItem("player_token") || "";
let _username = localStorage.getItem("player_username") || "";
let _worlds = [];

// ── auth helpers ──────────────────────────────────────────────────────────────

function authHeaders(extra = {}) {
  return { "Content-Type": "application/json", "Authorization": `Bearer ${_token}`, ...extra };
}

async function apiGet(path) {
  const res = await fetch(path, { headers: authHeaders() });
  if (res.status === 401) { doLogout(); throw new Error("Unauthorized"); }
  return res;
}

async function apiPost(path, body) {
  return fetch(path, { method: "POST", headers: authHeaders(), body: JSON.stringify(body) });
}

async function apiPatch(path, body) {
  return fetch(path, { method: "PATCH", headers: authHeaders(), body: JSON.stringify(body) });
}

// ── login ─────────────────────────────────────────────────────────────────────

$("d-login-btn").addEventListener("click", async () => {
  const u = $("d-user").value.trim();
  const p = $("d-pass").value;
  $("d-login-err").classList.add("hidden");
  if (!u || !p) { showLoginErr("Enter username and password."); return; }
  const res = await fetch("/player/auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: u, password: p }),
  });
  const data = await res.json();
  if (!res.ok) { showLoginErr(data.detail || "Login failed."); return; }
  _token = data.token;
  _username = data.username;
  localStorage.setItem("player_token", _token);
  localStorage.setItem("player_username", _username);
  showDashboard();
});

$("d-pass").addEventListener("keydown", e => { if (e.key === "Enter") $("d-login-btn").click(); });

function showLoginErr(msg) {
  $("d-login-err").textContent = msg;
  $("d-login-err").classList.remove("hidden");
}

function doLogout() {
  fetch("/player/logout", { method: "POST", headers: authHeaders() }).catch(() => {});
  _token = "";
  _username = "";
  localStorage.removeItem("player_token");
  localStorage.removeItem("player_username");
  $("dashboard").classList.add("hidden");
  $("login-overlay").classList.remove("hidden");
}

$("d-logout-btn").addEventListener("click", doLogout);

// ── tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll(".dtab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".dtab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".dtab-panel").forEach(p => p.classList.add("hidden"));
    btn.classList.add("active");
    $("dtab-" + btn.dataset.tab).classList.remove("hidden");
    if (btn.dataset.tab === "worlds") loadWorlds();
    if (btn.dataset.tab === "story")  loadStorySelect();
  });
});

// ── dashboard init ────────────────────────────────────────────────────────────

async function showDashboard() {
  $("login-overlay").classList.add("hidden");
  $("dashboard").classList.remove("hidden");
  $("dash-username").textContent = _username;
  await loadProfile();
}

// ── profile ───────────────────────────────────────────────────────────────────

async function loadProfile() {
  const res = await apiGet("/player/profile");
  if (!res.ok) return;
  const d = await res.json();
  $("p-email").value = d.email || "";
  $("p-sex").value   = d.sex   || "";
  $("p-age").value   = d.real_age || "";
  $("p-desc").value  = d.description || "";
}

$("p-save-btn").addEventListener("click", async () => {
  const res = await apiPatch("/player/profile", {
    email:       $("p-email").value,
    sex:         $("p-sex").value,
    real_age:    $("p-age").value,
    description: $("p-desc").value,
  });
  showSaveMsg("p-save-msg", res.ok, res.ok ? "Saved." : "Save failed.");
});

$("pw-save-btn").addEventListener("click", async () => {
  const old_pw = $("pw-old").value;
  const new_pw = $("pw-new").value;
  if (!old_pw || !new_pw) { showSaveMsg("pw-save-msg", false, "Fill both fields."); return; }
  const res = await apiPost("/player/change-password", { old_password: old_pw, new_password: new_pw });
  const ok = res.ok;
  const d  = await res.json();
  showSaveMsg("pw-save-msg", ok, ok ? "Password changed." : (d.detail || "Failed."));
  if (ok) { $("pw-old").value = ""; $("pw-new").value = ""; }
});

function showSaveMsg(id, ok, text) {
  const el = $(id);
  el.textContent = text;
  el.className = "save-msg " + (ok ? "ok-msg" : "err-msg");
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3000);
}

// ── worlds ────────────────────────────────────────────────────────────────────

async function loadWorlds() {
  const res = await apiGet("/player/worlds");
  if (!res.ok) return;
  _worlds = await res.json();
  const container = $("worlds-list");
  const empty = $("worlds-empty");
  if (!_worlds.length) { empty.classList.remove("hidden"); container.innerHTML = ""; return; }
  empty.classList.add("hidden");
  container.innerHTML = _worlds.map(w => `
    <div class="world-entry" data-wid="${w.world_id}">
      <div class="world-entry-info">
        <div class="we-name">${w.world_name}${w.online ? "" : ' <span class="muted">(offline)</span>'}</div>
        <div class="we-meta">
          Last room: ${w.last_room || "unknown"} &nbsp;·&nbsp; HP: ${w.hp}
        </div>
        <div class="we-context">
          <textarea class="ctx-input" placeholder="Personal notes for this world…" data-wid="${w.world_id}">${escHtml(w.context || "")}</textarea>
          <button class="ctx-save-btn" data-wid="${w.world_id}">Save notes</button>
        </div>
      </div>
      <div class="world-entry-actions">
        ${w.online ? `<a href="/" class="btn-link">Play</a>` : ""}
        <button class="view-story-btn" data-wid="${w.world_id}">Story</button>
      </div>
    </div>`).join("");

  // context save buttons
  container.querySelectorAll(".ctx-save-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const wid = btn.dataset.wid;
      const ctx = container.querySelector(`.ctx-input[data-wid="${wid}"]`).value;
      await apiPatch(`/player/worlds/${wid}/context`, { context: ctx });
    });
  });

  // story shortcut
  container.querySelectorAll(".view-story-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelector('.dtab[data-tab="story"]').click();
      setTimeout(() => {
        $("story-world-select").value = btn.dataset.wid;
        loadStory(btn.dataset.wid);
      }, 50);
    });
  });
}

// ── story ─────────────────────────────────────────────────────────────────────

async function loadStorySelect() {
  const res = await apiGet("/player/worlds");
  if (!res.ok) return;
  const worlds = await res.json();
  const sel = $("story-world-select");
  sel.innerHTML = '<option value="">— pick a world —</option>' +
    worlds.map(w => `<option value="${w.world_id}">${w.world_name}</option>`).join("");
}

$("story-world-select").addEventListener("change", e => {
  if (e.target.value) loadStory(e.target.value);
  else { $("story-log").innerHTML = ""; $("story-export-btn").classList.add("hidden"); }
});

$("story-export-btn").addEventListener("click", () => {
  const lines = [];
  document.querySelectorAll(".story-entry").forEach(el => {
    const ts   = el.querySelector(".story-ts")?.textContent || "";
    const body = el.querySelector(".story-body")?.innerText || "";
    lines.push(`[${ts.trim()}] ${body.replace(/\s+/g, " ").trim()}`);
  });
  const blob = new Blob([lines.join("\n")], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `story_${$("story-world-select").value}.txt`;
  a.click();
  URL.revokeObjectURL(url);
});

async function loadStory(worldId) {
  const res = await apiGet(`/player/story/${worldId}?n=300`);
  if (!res.ok) return;
  const d = await res.json();
  const entries = d.entries || [];
  const log = $("story-log");
  if (!entries.length) {
    log.innerHTML = '<p class="muted">No story entries yet — enter the world to start recording.</p>';
    $("story-export-btn").classList.add("hidden");
    return;
  }
  $("story-export-btn").classList.remove("hidden");
  log.innerHTML = entries.map(e => renderEntry(e)).join("");
}

function renderEntry(e) {
  const ts = (e.ts || "").replace("T", " ").replace("Z", "").slice(0, 16);
  let body = "";
  if (e.type === "enter_room") {
    const extras = [];
    if (e.npcs?.length) extras.push("NPCs: " + e.npcs.join(", "));
    if (e.items?.length) extras.push("Items: " + e.items.join(", "));
    if (e.exits?.length) extras.push("Exits: " + e.exits.join(", "));
    body = `<span class="story-label">Entered room:</span> <span class="story-room-name">${escHtml(e.room_name || "")}</span>` +
           (e.description ? `<div class="story-room-desc">${escHtml(e.description)}</div>` : "") +
           (extras.length  ? `<div class="story-extras">${extras.map(escHtml).join(" &nbsp;·&nbsp; ")}</div>` : "");
  } else if (e.type === "player_say") {
    body = `<span class="story-label">You:</span> ${escHtml(e.text || "")}`;
  } else if (e.type === "gm_reply") {
    body = `<span class="story-label">GM:</span> ${escHtml(e.text || "")}`;
  } else if (e.type === "npc_say") {
    body = `<span class="story-label">${escHtml(e.npc_name || "NPC")}:</span> ${escHtml(e.text || "")}`;
  } else {
    body = `<span class="story-label">${e.type}:</span> ${escHtml(JSON.stringify(e))}`;
  }
  return `<div class="story-entry story-type-${e.type}"><div class="story-ts">${ts}</div><div class="story-body">${body}</div></div>`;
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── auto-login if token exists ────────────────────────────────────────────────

(async () => {
  if (_token) {
    const res = await fetch("/player/profile", { headers: authHeaders() });
    if (res.ok) { showDashboard(); return; }
    // token expired — clear and show login
    localStorage.removeItem("player_token");
    localStorage.removeItem("player_username");
    _token = "";
  }
})();
