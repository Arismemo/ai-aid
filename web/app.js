// ai-aid dashboard — minimal GitHub-style.
// Same data model. New DOM (issue-list rows + Primer aesthetic).

const API_BASE = "";
const SSE_URL = "/events";

const STATUS_ICONS = {
  open:   "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0Zm0 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Z",
  closed: "M11.28 6.78a.75.75 0 0 0-1.06-1.06L7.25 8.69 5.78 7.22a.75.75 0 0 0-1.06 1.06l2 2a.75.75 0 0 0 1.06 0l3.5-3.5ZM16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0Zm-1.5 0a6.5 6.5 0 1 0-13 0 6.5 6.5 0 0 0 13 0Z",
};

const state = {
  cardsById: new Map(),
  lastEventId: 0,
  filter: { status: "open", search: "" },
};

const el = {
  cards: document.getElementById("cards"),
  template: document.getElementById("card-template"),
  tabs: document.querySelectorAll(".tab"),
  filterSearch: document.getElementById("filter-search"),
  liveBadge: document.getElementById("live-badge"),
  liveText: document.getElementById("live-text"),
  countOpen: document.getElementById("count-open"),
  countClosed: document.getElementById("count-closed"),
  empty: document.getElementById("empty-state"),
  hostName: document.getElementById("host-name"),
};

if (el.hostName) el.hostName.textContent = location.host || "localhost";

// ---------- formatting ----------

const REL_INTERVALS = [
  [60, "s"], [60, "m"], [24, "h"], [7, "d"], [4.345, "w"], [12, "mo"],
  [Number.POSITIVE_INFINITY, "y"],
];

function fmtRel(ms) {
  if (!ms) return "—";
  let diff = Math.max(0, (Date.now() - ms) / 1000);
  let unit = "s";
  for (const [step, u] of REL_INTERVALS) {
    if (diff < step) { unit = u; break; }
    diff /= step;
    unit = u;
  }
  return `${Math.floor(diff)}${unit} ago`;
}

function fmtAbs(ms) {
  if (!ms) return "";
  return new Date(ms).toLocaleString();
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function looksLikeCode(s) {
  if (!s) return false;
  return /\n/.test(s) || /[{};]\s*$/.test(s.trim()) ||
    /^\s*(def |class |import |from |const |let |function |SELECT |CREATE |#include )/.test(s);
}

// ---------- counters & filters ----------

function updateCounts() {
  let open = 0, closed = 0;
  for (const c of state.cardsById.values()) {
    if (c.data.status === "open") open++;
    else closed++;
  }
  el.countOpen.textContent = String(open);
  el.countClosed.textContent = String(closed);
  if (el.empty) {
    const visible = [...state.cardsById.values()].filter(c => c.node.style.display !== "none").length;
    el.empty.hidden = visible > 0;
  }
}

function applyFilter(card) {
  const d = card.data;
  const okStatus = state.filter.status === "all" || state.filter.status === d.status;
  const search = state.filter.search.toLowerCase();
  const okSearch =
    !search ||
    (d.goal || "").toLowerCase().includes(search) ||
    (d.context || "").toLowerCase().includes(search) ||
    (d.client_id || "").toLowerCase().includes(search);
  card.node.style.display = okStatus && okSearch ? "" : "none";
}

function applyFilterAll() {
  for (const card of state.cardsById.values()) applyFilter(card);
  updateCounts();
}

// ---------- rendering ----------

function renderChrome(node, d) {
  node.dataset.id = d.id;
  node.dataset.status = d.status;

  const path = node.querySelector(".status-path");
  if (path) path.setAttribute("d", STATUS_ICONS[d.status] || STATUS_ICONS.open);

  const title = node.querySelector(".issue-title");
  title.textContent = d.goal || "(no goal)";

  const badges = node.querySelector(".issue-badges");
  badges.innerHTML = "";
  if (d.model) {
    const span = document.createElement("span");
    span.className = "label label-model";
    span.textContent = d.model;
    badges.appendChild(span);
  }

  node.querySelector(".meta-id").textContent = `#${d.id.slice(0, 7)}`;
  const t = node.querySelector(".meta-time");
  t.textContent = fmtRel(d.created_at);
  t.title = fmtAbs(d.created_at);
  node.querySelector(".meta-client").textContent = d.client_id || "?";

  const ans = d.answer_count ?? 0;
  const pill = node.querySelector(".ans-pill");
  pill.querySelector(".ans-count").textContent = String(ans);
  pill.dataset.has = ans > 0 ? "true" : "false";
}

function renderDetail(node, d) {
  const dl = node.querySelector(".detail-fields");
  dl.innerHTML = "";
  const fields = [
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
    if (looksLikeCode(v)) {
      const pre = document.createElement("pre");
      pre.textContent = v;
      dd.appendChild(pre);
    } else {
      dd.textContent = v;
    }
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  const ansBox = node.querySelector(".detail-answers");
  ansBox.innerHTML = "";
  for (const a of d.answers || []) ansBox.appendChild(renderAnswer(a));
}

function renderAnswer(a) {
  const div = document.createElement("div");
  div.className = "answer";
  div.dataset.id = a.id;

  const sum = document.createElement("p");
  sum.className = "ans-summary";
  sum.textContent = a.summary;
  div.appendChild(sum);

  const meta = document.createElement("p");
  meta.className = "ans-meta";
  meta.innerHTML = `<b>${escapeHtml(a.solver_client_id)}</b> answered with ${escapeHtml(a.solver_model)} · ${escapeHtml(fmtRel(a.created_at))}`;
  div.appendChild(meta);

  const sections = [
    ["solution", a.solution, true],
    ["reasoning", a.reasoning, false],
    ["caveats", a.caveats, false],
  ];
  for (const [k, v, isCode] of sections) {
    if (!v) continue;
    const wrap = document.createElement("div");
    wrap.className = "ans-section";
    const key = document.createElement("span");
    key.className = "ans-key";
    key.textContent = k;
    wrap.appendChild(key);
    if (isCode || looksLikeCode(v)) {
      const pre = document.createElement("pre");
      pre.className = "ans-code";
      pre.textContent = v;
      wrap.appendChild(pre);
    } else {
      const val = document.createElement("div");
      val.className = "ans-val";
      val.textContent = v;
      wrap.appendChild(val);
    }
    div.appendChild(wrap);
  }
  return div;
}

function buildCard(d, opts = { incoming: false }) {
  const node = el.template.content.firstElementChild.cloneNode(true);
  renderChrome(node, d);

  // Title click toggles detail
  const title = node.querySelector(".issue-title");
  title.addEventListener("click", (e) => {
    e.preventDefault();
    const det = node.querySelector(".issue-detail");
    det.open = !det.open;
  });

  node.querySelector(".act-close").addEventListener("click", () => closeCard(d.id));
  node.querySelector(".act-delete").addEventListener("click", () => deleteCard(d.id));

  const detail = node.querySelector(".issue-detail");
  detail.addEventListener("toggle", async (ev) => {
    if (!ev.target.open) return;
    try {
      const fresh = await fetchJson(`/api/requests/${d.id}`);
      Object.assign(d, fresh);
      renderDetail(node, d);
    } catch (e) {
      console.warn("detail fetch failed", e);
    }
  });

  if (opts.incoming) {
    node.classList.add("is-new");
    setTimeout(() => node.classList.remove("is-new"), 1300);
  }
  return node;
}

function upsertCard(d, opts = {}) {
  let entry = state.cardsById.get(d.id);
  if (!entry) {
    const node = buildCard(d, opts);
    entry = { node, data: d };
    state.cardsById.set(d.id, entry);
    el.cards.prepend(node);
  } else {
    entry.data = { ...entry.data, ...d };
    renderChrome(entry.node, entry.data);
  }
  applyFilter(entry);
  updateCounts();
}

function removeCard(id) {
  const entry = state.cardsById.get(id);
  if (!entry) return;
  entry.node.style.transition = "opacity 0.25s, transform 0.25s";
  entry.node.style.opacity = "0";
  entry.node.style.transform = "translateY(-4px)";
  setTimeout(() => entry.node.remove(), 250);
  state.cardsById.delete(id);
  updateCounts();
}

function bumpAnswerCount(rid, ans) {
  const entry = state.cardsById.get(rid);
  if (!entry) return;
  entry.data.answer_count = (entry.data.answer_count || 0) + 1;
  if (Array.isArray(entry.data.answers)) entry.data.answers.push(ans);
  renderChrome(entry.node, entry.data);
  const det = entry.node.querySelector(".issue-detail");
  if (det.open && Array.isArray(entry.data.answers)) {
    entry.node.querySelector(".detail-answers").appendChild(renderAnswer(ans));
  }
}

function markClosed(rid, closedAt) {
  const entry = state.cardsById.get(rid);
  if (!entry) return;
  entry.data.status = "closed";
  entry.data.closed_at = closedAt;
  renderChrome(entry.node, entry.data);
  applyFilter(entry);
  updateCounts();
}

// ---------- API ----------

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
  if (!confirm(`Close request #${id.slice(0, 7)}?`)) return;
  await fetchJson(`/api/requests/${id}/close`, { method: "POST" });
}

async function deleteCard(id) {
  if (!confirm(`Permanently delete request #${id.slice(0, 7)}? This cannot be undone.`)) return;
  await fetchJson(`/api/requests/${id}`, { method: "DELETE" });
}

// ---------- SSE ----------

function setLive(stateName, label) {
  el.liveBadge.dataset.state = stateName;
  if (el.liveText) el.liveText.textContent = label;
}

function connectSse() {
  const url = `${SSE_URL}?last_event_id=${state.lastEventId}`;
  const es = new EventSource(url);
  es.onopen = () => setLive("connected", "live");
  es.onerror = () => setLive("reconnecting", "reconnecting");

  es.addEventListener("request.created", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    upsertCard(d, { incoming: true });
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
    console.warn("SSE replay-gap, refetching", ev.data);
    state.lastEventId = 0;
    state.cardsById.clear();
    el.cards.innerHTML = "";
    loadInitial();
  });
}

// ---------- wiring ----------

el.tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    el.tabs.forEach((b) => b.classList.toggle("is-active", b === btn));
    state.filter.status = btn.dataset.status;
    applyFilterAll();
  });
});
el.filterSearch.addEventListener("input", (e) => {
  state.filter.search = e.target.value;
  applyFilterAll();
});

setInterval(() => {
  for (const c of state.cardsById.values()) {
    const t = c.node.querySelector(".meta-time");
    if (t) t.textContent = fmtRel(c.data.created_at);
  }
}, 60_000);

(async () => {
  try {
    await loadInitial();
    connectSse();
  } catch (e) {
    console.error("Dashboard init failed", e);
    setLive("disconnected", "offline");
  }
})();
