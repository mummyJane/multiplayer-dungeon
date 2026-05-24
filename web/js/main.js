"use strict";

const $ = id => document.getElementById(id);

let ws = null;
let selectedWorld = null;
let pendingAuth = null;   // { action, username, password } — set before WS opens

// ── helpers ──────────────────────────────────────────────────────────────────

function addMessage(text, cls = "") {
  const div = document.createElement("div");
  div.className = "msg" + (cls ? " " + cls : "");
  div.textContent = text;
  $("messages").appendChild(div);
  $("output-panel").scrollTop = $("output-panel").scrollHeight;
}

function updateRoom(data) {
  $("room-name").textContent = data.name;
  $("room-desc").textContent = data.description;
  $("exits").textContent = data.exits.join(", ") || "none";

  const parts = [];
  if (data.players?.length)   parts.push("Players: " + data.players.join(", "));
  if (data.npcs?.length)      parts.push("NPCs: " + data.npcs.join(", "));
  if (data.monsters?.length)  parts.push("Enemies: " + data.monsters.join(", "));
  if (data.items?.length)     parts.push("Items: " + data.items.join(", "));
  $("people-bar").innerHTML = parts.map(p => `<span>${p}</span>`).join("&ensp;·&ensp;");
}

function updateStatus(data) {
  const maxHp = data.max_hp || 100;
  const hp    = data.hp ?? maxHp;
  const pct   = Math.max(0, Math.min(100, Math.round(hp / maxHp * 100)));
  $("status-hp").innerHTML =
    `<div class="hp-label">HP ${hp}/${maxHp}</div>` +
    `<div class="hp-bar"><div class="hp-fill" style="width:${pct}%"></div></div>`;

  const invEl = $("status-inv");
  if (data.inventory?.length) {
    invEl.textContent = "Inv: " + data.inventory.join(", ");
    invEl.classList.remove("hidden");
  } else {
    invEl.classList.add("hidden");
  }

  // worn clothing
  const wornEl = $("status-worn");
  const worn = data.worn || {};
  const wornEntries = Object.entries(worn);
  if (wornEntries.length) {
    wornEl.innerHTML = wornEntries
      .map(([slot, name]) => `<div class="worn-row"><span class="worn-slot">${slot}</span> ${name}</div>`)
      .join("");
    wornEl.classList.remove("hidden");
  } else {
    wornEl.classList.add("hidden");
  }

  // active effects from worn items
  const effectsEl = $("status-effects");
  const effects = data.effects || [];
  if (effects.length) {
    effectsEl.innerHTML = effects.map(e =>
      `<span class="effect-chip effect-${e}">${e.replace(/_/g," ")}</span>`
    ).join("");
    effectsEl.classList.remove("hidden");
  } else {
    effectsEl.classList.add("hidden");
  }

  const flagsEl = $("status-flags");
  const flags = data.flags || {};
  const entries = Object.entries(flags);
  if (entries.length) {
    flagsEl.innerHTML = entries.map(([k, v]) => {
      const label = v === true ? k : `${k}: ${v}`;
      return `<span class="flag-chip">${label}</span>`;
    }).join("");
    flagsEl.classList.remove("hidden");
  } else {
    flagsEl.classList.add("hidden");
  }

  $("status-panel").classList.remove("hidden");
}

function showAuthError(msg) {
  const el = $("auth-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearAuthError() {
  $("auth-error").classList.add("hidden");
}

// ── world list ───────────────────────────────────────────────────────────────

async function loadWorlds() {
  try {
    const res = await fetch("/worlds");
    const worlds = await res.json();
    const list = $("world-list");
    if (!worlds.length) {
      list.innerHTML = "<p class='muted'>No worlds available yet.</p>";
      return;
    }
    list.innerHTML = "";
    worlds.forEach(w => {
      const card = document.createElement("div");
      card.className = "world-card";
      card.innerHTML = `
        <div class="world-card-inner">
          <div class="wname">${w.name}</div>
          <div class="wdesc">${w.description || ""}</div>
        </div>
        <div class="wpop">${w.players}/${w.max_players} players</div>`;
      card.addEventListener("click", () => pickWorld(w));
      list.appendChild(card);
    });
  } catch (e) {
    $("world-error").textContent = "Could not load worlds.";
    $("world-error").classList.remove("hidden");
  }
}

function pickWorld(w) {
  selectedWorld = w;
  $("auth-world-title").textContent = w.name;
  $("world-overlay").classList.add("hidden");
  $("auth-overlay").classList.remove("hidden");
  clearAuthError();
  $("login-user").focus();
}

// ── auth tab switching ────────────────────────────────────────────────────────

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".auth-tab").forEach(t => t.classList.add("hidden"));
    btn.classList.add("active");
    $("tab-" + btn.dataset.tab).classList.remove("hidden");
    clearAuthError();
  });
});

$("auth-back-btn").addEventListener("click", () => {
  $("auth-overlay").classList.add("hidden");
  $("world-overlay").classList.remove("hidden");
  selectedWorld = null;
});

// ── auth actions ──────────────────────────────────────────────────────────────

$("login-btn").addEventListener("click", () => {
  const u = $("login-user").value.trim();
  const p = $("login-pass").value;
  if (!u || !p) { showAuthError("Enter username and password."); return; }
  pendingAuth = { action: "login", username: u, password: p };
  openWS();
});

$("reg-btn").addEventListener("click", () => {
  const u = $("reg-user").value.trim();
  const p = $("reg-pass").value;
  if (!u || !p) { showAuthError("Enter username and password."); return; }
  pendingAuth = { action: "register", username: u, password: p };
  openWS();
});

$("guest-btn").addEventListener("click", () => {
  const name = $("guest-name").value.trim();
  if (!name) { showAuthError("Enter a display name."); return; }
  pendingAuth = { action: "guest", username: "", password: "", guestName: name };
  openWS();
});

// Enter key shortcuts
$("login-pass").addEventListener("keydown", e => { if (e.key === "Enter") $("login-btn").click(); });
$("reg-pass").addEventListener("keydown",   e => { if (e.key === "Enter") $("reg-btn").click(); });
$("guest-name").addEventListener("keydown", e => { if (e.key === "Enter") $("guest-btn").click(); });

// ── back button (name overlay) ────────────────────────────────────────────────

$("back-btn").addEventListener("click", () => {
  $("name-overlay").classList.add("hidden");
  $("auth-overlay").classList.remove("hidden");
  selectedWorld = null;
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
});

// ── WebSocket ────────────────────────────────────────────────────────────────

function openWS() {
  if (!selectedWorld || !pendingAuth) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${selectedWorld.id}`);

  ws.onopen = () => addMessage("Connecting…", "system");

  ws.onmessage = evt => {
    const msg = JSON.parse(evt.data);
    switch (msg.type) {

      case "auth_prompt":
        ws.send(JSON.stringify({
          action:   pendingAuth.action,
          username: pendingAuth.username,
          password: pendingAuth.password,
        }));
        break;

      case "auth_ok":
        clearAuthError();
        $("auth-overlay").classList.add("hidden");
        if (pendingAuth.action === "guest") {
          // guest already provided a name — send directly when prompted
        }
        break;

      case "auth_error":
        showAuthError(msg.text);
        ws.onclose = null;
        ws.close();
        ws = null;
        break;

      case "prompt":
        if (pendingAuth.action === "guest") {
          ws.send(JSON.stringify({ text: pendingAuth.guestName }));
        } else {
          // logged-in users don't need the name prompt; server uses their username
          // but just in case:
          ws.send(JSON.stringify({ text: pendingAuth.username }));
        }
        break;

      case "welcome":
        $("world-tag").textContent = msg.world;
        addMessage(`Welcome to ${msg.world}, ${msg.name}!`, "system");
        $("name-overlay").classList.add("hidden");
        $("auth-overlay").classList.add("hidden");
        $("quick-actions").classList.remove("hidden");
        pendingAuth = null;
        break;

      case "room":
        updateRoom(msg);
        break;

      case "message":
        addMessage(msg.text);
        break;

      case "status":
        updateStatus(msg);
        break;

      default:
        console.warn("Unknown msg type:", msg.type);
    }
  };

  ws.onclose = () => {
    addMessage("Disconnected.", "system");
    selectedWorld = null;
    pendingAuth = null;
    $("quick-actions").classList.add("hidden");
    loadWorlds();
    $("world-overlay").classList.remove("hidden");
    $("auth-overlay").classList.add("hidden");
    $("name-overlay").classList.add("hidden");
  };

  ws.onerror = () => addMessage("Connection error.", "system");
}

function sendCommand() {
  const input = $("cmd-input");
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  addMessage(`> ${text}`, "system");
  ws.send(JSON.stringify({ text }));
  input.value = "";
}

// ── switch world ──────────────────────────────────────────────────────────────

$("switch-world-btn").addEventListener("click", () => {
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  $("quick-actions").classList.add("hidden");
  selectedWorld = null;
  pendingAuth = null;
  loadWorlds();
  $("world-overlay").classList.remove("hidden");
  $("auth-overlay").classList.add("hidden");
  $("name-overlay").classList.add("hidden");
});

// ── event wiring ─────────────────────────────────────────────────────────────

$("cmd-send").addEventListener("click", sendCommand);
$("cmd-input").addEventListener("keydown", e => { if (e.key === "Enter") sendCommand(); });

// ── init ─────────────────────────────────────────────────────────────────────
loadWorlds();
