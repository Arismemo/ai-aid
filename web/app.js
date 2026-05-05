const API_BASE = "";
const SSE_URL = "/events";

const state = {
  cardsById: new Map(),
  lastEventId: 0,
  filter: { status: "open", search: "" },
};

const el = {
  cards: document.getElementById("cards"),
  template: document.getElementById("card-template"),
  filterStatus: document.getElementById("filter-status"),
  filterSearch: document.getElementById("filter-search"),
  liveBadge: document.getElementById("live-badge"),
  countOpen: document.getElementById("count-open"),
  countClosed: document.getElementById("count-closed"),
};

function fmtTime(ms) {
  if (!ms) return "";
  const d = new Date(ms);
  return d.toLocaleString();
}

function updateCounts() {
  let open = 0, closed = 0;
  for (const c of state.cardsById.values()) {
    if (c.data.status === "open") open++;
    else closed++;
  }
  el.countOpen.textContent = `open: ${open}`;
  el.countClosed.textContent = `closed: ${closed}`;
}

function applyFilter(card) {
  const d = card.data;
  const okStatus =
    state.filter.status === "all" ||
    state.filter.status === d.status;
  const search = state.filter.search.toLowerCase();
  const okSearch =
    !search ||
    (d.goal || "").toLowerCase().includes(search) ||
    (d.context || "").toLowerCase().includes(search);
  card.node.style.display = okStatus && okSearch ? "" : "none";
}

function applyFilterAll() {
  for (const card of state.cardsById.values()) applyFilter(card);
}

function renderCardChrome(node, d) {
  node.dataset.id = d.id;
  node.dataset.status = d.status;
  node.querySelector(".badge-id").textContent = `#${d.id.slice(0, 6)}`;
  node.querySelector(".badge-status").textContent = d.status;
  node.querySelector(".badge-model").textContent = d.model || "?";
  node.querySelector(".badge-time").textContent = fmtTime(d.created_at);
  node.querySelector(".goal").textContent = d.goal || "(no goal)";
  node.querySelector(".client-id").textContent = d.client_id || "?";
  node.querySelector(".answer-count").textContent = d.answer_count ?? 0;
}

function renderCardBody(node, d) {
  const body = node.querySelector(".full-body");
  body.innerHTML = "";
  const fields = [
    ["goal", d.goal],
    ["context", d.context],
    ["tried", d.tried],
    ["error", d.error],
    ["constraints", d.constraints],
    ["question", d.question],
  ];
  for (const [k, v] of fields) {
    if (!v) continue;
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    body.appendChild(dt);
    body.appendChild(dd);
  }
  const answersBox = node.querySelector(".answers");
  answersBox.innerHTML = "";
  for (const a of d.answers || []) {
    answersBox.appendChild(renderAnswer(a));
  }
}

function renderAnswer(a) {
  const div = document.createElement("div");
  div.className = "answer";
  div.dataset.id = a.id;
  div.innerHTML = `
    <p><strong>${escapeHtml(a.summary)}</strong>
      <small>by ${escapeHtml(a.solver_client_id)} (${escapeHtml(a.solver_model)}) at ${fmtTime(a.created_at)}</small>
    </p>
  `;
  if (a.solution) {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = a.solution;
    pre.appendChild(code);
    div.appendChild(pre);
    if (window.hljs) hljs.highlightElement(code);
  }
  if (a.reasoning) {
    const p = document.createElement("p");
    p.innerHTML = `<em>reasoning:</em> ${escapeHtml(a.reasoning)}`;
    div.appendChild(p);
  }
  if (a.caveats) {
    const p = document.createElement("p");
    p.innerHTML = `<em>caveats:</em> ${escapeHtml(a.caveats)}`;
    div.appendChild(p);
  }
  return div;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function buildCard(d) {
  const node = el.template.content.firstElementChild.cloneNode(true);
  renderCardChrome(node, d);
  node.querySelector(".btn-close").addEventListener("click", () => closeCard(d.id));
  node.querySelector(".btn-delete").addEventListener("click", () => deleteCard(d.id));
  node.querySelector("details").addEventListener("toggle", async (ev) => {
    if (!ev.target.open) return;
    const detail = await fetchJson(`/api/requests/${d.id}`);
    Object.assign(d, detail);
    renderCardBody(node, d);
  });
  return node;
}

function upsertCard(d) {
  let entry = state.cardsById.get(d.id);
  if (!entry) {
    const node = buildCard(d);
    entry = { node, data: d };
    state.cardsById.set(d.id, entry);
    el.cards.prepend(node);
    node.classList.add("flash");
    setTimeout(() => node.classList.remove("flash"), 1100);
  } else {
    entry.data = { ...entry.data, ...d };
    renderCardChrome(entry.node, entry.data);
  }
  applyFilter(entry);
  updateCounts();
}

function removeCard(id) {
  const entry = state.cardsById.get(id);
  if (!entry) return;
  entry.node.remove();
  state.cardsById.delete(id);
  updateCounts();
}

function bumpAnswerCount(rid, ans) {
  const entry = state.cardsById.get(rid);
  if (!entry) return;
  entry.data.answer_count = (entry.data.answer_count || 0) + 1;
  if (entry.data.answers) entry.data.answers.push(ans);
  renderCardChrome(entry.node, entry.data);
  if (entry.node.querySelector("details").open && entry.data.answers) {
    entry.node.querySelector(".answers").appendChild(renderAnswer(ans));
  }
  updateCounts();
}

function markClosed(rid, closedAt) {
  const entry = state.cardsById.get(rid);
  if (!entry) return;
  entry.data.status = "closed";
  entry.data.closed_at = closedAt;
  renderCardChrome(entry.node, entry.data);
  applyFilter(entry);
  updateCounts();
}

async function fetchJson(path, init) {
  const resp = await fetch(API_BASE + path, init);
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.status === 204 ? null : resp.json();
}

async function loadInitial() {
  const list = await fetchJson("/api/requests?status=all");
  list.sort((a, b) => b.created_at - a.created_at);
  for (const d of list) upsertCard(d);
}

async function closeCard(id) {
  if (!confirm(`Close request ${id.slice(0, 6)}?`)) return;
  await fetchJson(`/api/requests/${id}/close`, { method: "POST" });
}

async function deleteCard(id) {
  if (!confirm(`Permanently DELETE request ${id.slice(0, 6)}? This cannot be undone.`)) return;
  await fetchJson(`/api/requests/${id}`, { method: "DELETE" });
}

function connectSse() {
  const url = `${SSE_URL}?last_event_id=${state.lastEventId}`;
  const es = new EventSource(url);
  es.onopen = () => { el.liveBadge.dataset.state = "connected"; el.liveBadge.textContent = "● live"; };
  es.onerror = () => { el.liveBadge.dataset.state = "reconnecting"; el.liveBadge.textContent = "● reconnecting"; };

  es.addEventListener("request.created", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    upsertCard(d);
  });
  es.addEventListener("answer.created", (ev) => {
    const a = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    bumpAnswerCount(a.request_id, a);
  });
  es.addEventListener("request.closed", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    markClosed(d.id, d.closed_at);
  });
  es.addEventListener("request.deleted", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    removeCard(d.id);
  });
  es.addEventListener("replay-gap", (ev) => {
    console.warn("SSE replay-gap, refetching all", ev.data);
    state.lastEventId = 0;
    state.cardsById.clear();
    el.cards.innerHTML = "";
    loadInitial();
  });
}

el.filterStatus.addEventListener("change", (e) => {
  state.filter.status = e.target.value;
  applyFilterAll();
});
el.filterSearch.addEventListener("input", (e) => {
  state.filter.search = e.target.value;
  applyFilterAll();
});

(async () => {
  try {
    await loadInitial();
    connectSse();
  } catch (e) {
    console.error("Dashboard init failed", e);
    el.liveBadge.dataset.state = "disconnected";
    el.liveBadge.textContent = "● error";
  }
})();
