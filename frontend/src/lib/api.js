import { openEventStream } from "./sse";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api/v1";

function uid() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  if (res.status === 204) {
    return null;
  }
  return res.json();
}

export function createPlayer(payload) {
  return request("/players", {
    method: "POST",
    headers: { "Idempotency-Key": uid() },
    body: JSON.stringify(payload),
  });
}

export function startMonthStream(playerId) {
  return openEventStream(`${API_BASE}/players/${playerId}/start-month`, {
    method: "POST",
    headers: { "Idempotency-Key": uid() },
  });
}

export function decideStream(playerId, payload) {
  return openEventStream(`${API_BASE}/players/${playerId}/decide`, {
    method: "POST",
    headers: { "Idempotency-Key": uid() },
    body: payload,
  });
}

export function endMonth(playerId) {
  return request(`/players/${playerId}/end-month`, {
    method: "POST",
    headers: { "Idempotency-Key": uid() },
  });
}

export function patchPlayer(playerId, payload) {
  return request(`/players/${playerId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getState(playerId) {
  return request(`/players/${playerId}/state`);
}

export function getMessages(playerId, month) {
  const query = month == null ? "" : `?month=${month}`;
  return request(`/players/${playerId}/messages${query}`);
}

export function markMessageRead(playerId, messageId, isRead = true) {
  return request(`/players/${playerId}/messages/${messageId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_read: Boolean(isRead) }),
  });
}

export function getLeaderboard() {
  return request("/leaderboard");
}

export function getCost(playerId) {
  return request(`/players/${playerId}/cost`);
}

export function getAutopsy(playerId) {
  return request(`/players/${playerId}/autopsy`);
}
