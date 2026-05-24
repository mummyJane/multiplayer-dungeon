"use strict";

const $ = id => document.getElementById(id);
let adminKey = "";

function authHeaders() {
  return { "Content-Type": "application/json", "x-admin-key": adminKey };
}

// ── auth ──────────────────────────────────────────────────────────────────────

$("auth-btn").addEventListener("click", async () => {
  adminKey = $("admin-key").value.trim();
  const res = await fetch("/admin/worlds", { headers: authHeaders() });
  if (res.ok) {
    $("auth-status").textContent = "✓ authenticated";
    loadWorlds();
  } else {
    $("auth-status").textContent = "✗ wrong key";
    adminKey = "";
  }
});

// ── world list ────────────────────────────────────────────────────────────────

async function loadWorlds() {
  const res = await fetch("/admin/worlds", { headers: authHeaders() });
  if (!res.ok) return;
  const worlds = await res.json();
  const tbody = $("worlds-tbody");
  tbody.innerHTML = "";
  worlds.forEach(w => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${w.id}</td>
      <td>${w.name}</td>
      <td>${w.players}/${w.max_players}</td>
      <td>
        <button onclick="reloadScripts('${w.id}')">Reload scripts</button>
        <button onclick="removeWorld('${w.id}')" class="muted">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
}

async function reloadScripts(worldId) {
  const res = await fetch(`/admin/worlds/${worldId}/reload-scripts`, {
    method: "POST", headers: authHeaders()
  });
  alert(res.ok ? "Scripts reloaded." : "Error reloading scripts.");
}

async function removeWorld(worldId) {
  if (!confirm(`Delete world '${worldId}'?`)) return;
  const res = await fetch(`/admin/worlds/${worldId}`, {
    method: "DELETE", headers: authHeaders()
  });
  if (res.ok) loadWorlds();
}

// ── generate world ────────────────────────────────────────────────────────────

$("generate-btn").addEventListener("click", async () => {
  const theme = $("theme-input").value.trim();
  if (!theme) return;
  const status = $("generate-status");
  status.textContent = "Asking Claude… (this may take 10-20s)";
  status.className = "muted";
  try {
    const res = await fetch("/admin/worlds/generate", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ theme }),
    });
    const data = await res.json();
    if (res.ok) {
      status.textContent = `✓ World '${data.name}' created (id: ${data.world_id})`;
      status.className = "";
      $("theme-input").value = "";
      loadWorlds();
    } else {
      status.textContent = `✗ ${data.detail || "Error"}`;
      status.className = "error";
    }
  } catch (e) {
    status.textContent = "✗ Request failed";
    status.className = "error";
  }
});

// ── manual create ─────────────────────────────────────────────────────────────

$("manual-btn").addEventListener("click", async () => {
  const id = $("manual-id").value.trim();
  const name = $("manual-name").value.trim();
  if (!id || !name) return;
  const status = $("manual-status");
  const res = await fetch("/admin/worlds/manual", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ id, name }),
  });
  const data = await res.json();
  if (res.ok) {
    status.textContent = `✓ World '${data.name}' created`;
    $("manual-id").value = "";
    $("manual-name").value = "";
    loadWorlds();
  } else {
    status.textContent = `✗ ${data.detail || "Error"}`;
  }
});
