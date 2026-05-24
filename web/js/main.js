"use strict";

const $ = id => document.getElementById(id);

let ws = null;
let awaitingName = false;

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
  const others = data.players || [];
  if (others.length > 0) {
    $("players-here").textContent = others.join(", ");
    $("players-bar").hidden = false;
  } else {
    $("players-bar").hidden = true;
  }
}

function connect(playerName) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    addMessage("Connected.", "system");
  };

  ws.onmessage = evt => {
    const msg = JSON.parse(evt.data);

    switch (msg.type) {
      case "prompt":
        awaitingName = true;
        // respond immediately with the name we already have
        ws.send(JSON.stringify({ text: playerName }));
        awaitingName = false;
        break;

      case "welcome":
        addMessage(`Welcome, ${msg.name}!`, "system");
        $("connect-overlay").classList.add("hidden");
        break;

      case "room":
        updateRoom(msg);
        break;

      case "message":
        addMessage(msg.text);
        break;

      default:
        console.warn("Unknown message type:", msg.type);
    }
  };

  ws.onclose = () => {
    addMessage("Disconnected.", "system");
    $("connect-overlay").classList.remove("hidden");
  };

  ws.onerror = () => {
    addMessage("Connection error.", "system");
  };
}

function sendCommand() {
  const input = $("cmd-input");
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  addMessage(`> ${text}`, "system");
  ws.send(JSON.stringify({ text }));
  input.value = "";
}

// --- event wiring ---

$("connect-btn").addEventListener("click", () => {
  const name = $("name-input").value.trim();
  if (!name) return;
  connect(name);
});

$("name-input").addEventListener("keydown", e => {
  if (e.key === "Enter") $("connect-btn").click();
});

$("cmd-send").addEventListener("click", sendCommand);

$("cmd-input").addEventListener("keydown", e => {
  if (e.key === "Enter") sendCommand();
});
