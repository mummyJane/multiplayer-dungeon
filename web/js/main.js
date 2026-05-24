"use strict";

const $ = id => document.getElementById(id);

let ws = null;
let selectedWorld = null;

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
  $("people-bar").innerHTML = parts.map(p => `<span>${p}</span>`).join("&ensp;·&ensp;");
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
  $("name-world-title").textContent = w.name;
  $("world-overlay").classList.add("hidden");
  $("name-overlay").classList.remove("hidden");
  $("name-input").focus();
}

$("back-btn").addEventListener("click", () => {
  $("name-overlay").classList.add("hidden");
  $("world-overlay").classList.remove("hidden");
  selectedWorld = null;
});

// ── WebSocket ────────────────────────────────────────────────────────────────

function connect(playerName) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${selectedWorld.id}`);

  ws.onopen = () => addMessage("Connecting…", "system");

  ws.onmessage = evt => {
    const msg = JSON.parse(evt.data);
    switch (msg.type) {
      case "prompt":
        ws.send(JSON.stringify({ text: playerName }));
        break;
      case "welcome":
        $("world-tag").textContent = msg.world;
        addMessage(`Welcome to ${msg.world}, ${msg.name}!`, "system");
        $("name-overlay").classList.add("hidden");
        break;
      case "room":
        updateRoom(msg);
        break;
      case "message":
        addMessage(msg.text);
        break;
      default:
        console.warn("Unknown msg type:", msg.type);
    }
  };

  ws.onclose = () => {
    addMessage("Disconnected.", "system");
    selectedWorld = null;
    loadWorlds();
    $("world-overlay").classList.remove("hidden");
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

// ── event wiring ─────────────────────────────────────────────────────────────

$("name-btn").addEventListener("click", () => {
  const name = $("name-input").value.trim();
  if (!name || !selectedWorld) return;
  connect(name);
});

$("name-input").addEventListener("keydown", e => { if (e.key === "Enter") $("name-btn").click(); });
$("cmd-send").addEventListener("click", sendCommand);
$("cmd-input").addEventListener("keydown", e => { if (e.key === "Enter") sendCommand(); });

// ── init ──────────────────────────────────────────────────────────────────────
loadWorlds();
