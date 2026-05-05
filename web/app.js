// ai-aid dashboard — minimal GitHub-style.
// Same data model. New DOM (issue-list rows + Primer aesthetic).

const API_BASE = "";
const SSE_URL = "/events";

const STATUS_ICONS = {
  open:   "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0Zm0 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Z",
  closed: "M11.28 6.78a.75.75 0 0 0-1.06-1.06L7.25 8.69 5.78 7.22a.75.75 0 0 0-1.06 1.06l2 2a.75.75 0 0 0 1.06 0l3.5-3.5ZM16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0Zm-1.5 0a6.5 6.5 0 1 0-13 0 6.5 6.5 0 0 0 13 0Z",
};

const SORT_KEY = "aid-sort";
const ACTOR_KEY = "aid-actor";
const VALID_SORTS = ["newest", "oldest", "answered", "active", "upvoted"];

const state = {
  cardsById: new Map(),
  lastEventId: 0,
  filter: { status: "open", search: "" },
  sort: VALID_SORTS.includes(localStorage.getItem(SORT_KEY))
    ? localStorage.getItem(SORT_KEY) : "newest",
  actor: localStorage.getItem(ACTOR_KEY) || "",
  focusedId: null,
};

const el = {
  cards: document.getElementById("cards"),
  template: document.getElementById("card-template"),
  tabs: document.querySelectorAll(".tab"),
  filterSearch: document.getElementById("filter-search"),
  sortSelect: document.getElementById("sort-select"),
  actorInput: document.getElementById("actor-input"),
  liveBadge: document.getElementById("live-badge"),
  liveText: document.getElementById("live-text"),
  countOpen: document.getElementById("count-open"),
  countClosed: document.getElementById("count-closed"),
  empty: document.getElementById("empty-state"),
  hostName: document.getElementById("host-name"),
  modalRoot: document.getElementById("modal-root"),
  modalBackdrop: document.getElementById("modal-backdrop"),
  modal: document.getElementById("detail-modal"),
  modalStatus: document.getElementById("modal-status"),
  modalId: document.getElementById("modal-id"),
  modalGoal: document.getElementById("modal-goal"),
  modalMeta: document.getElementById("modal-meta"),
  modalFields: document.getElementById("modal-fields"),
  modalAnswers: document.getElementById("modal-answers"),
  modalCloseBtn: document.getElementById("modal-close"),
  modalCloseReq: document.getElementById("modal-close-req"),
  modalDeleteReq: document.getElementById("modal-delete-req"),
};

const modalState = { id: null };

if (el.hostName) el.hostName.textContent = location.host || "localhost";
if (el.sortSelect) el.sortSelect.value = state.sort;
if (el.actorInput) el.actorInput.value = state.actor;

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

function highlight(pre) {
  if (!window.hljs) return;
  // hljs needs a <code> child; wrap if missing
  let code = pre.querySelector("code");
  if (!code) {
    code = document.createElement("code");
    code.textContent = pre.textContent;
    pre.textContent = "";
    pre.appendChild(code);
  }
  try { window.hljs.highlightElement(code); } catch (_) { /* noop */ }
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
    const visible = visibleCards().length;
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

// ---------- sort ----------

function sortKey(d) {
  switch (state.sort) {
    case "oldest":   return d.created_at;
    case "newest":   return -d.created_at;
    case "answered": return -((d.answer_count || 0) * 1e15) - d.created_at;
    case "active":   return -(d.closed_at || d.created_at);
    case "upvoted":  return -((d.top_votes || 0) * 1e15) - d.created_at;
    default:         return -d.created_at;
  }
}

function applySort() {
  const entries = [...state.cardsById.values()];
  entries.sort((a, b) => sortKey(a.data) - sortKey(b.data));
  for (const e of entries) el.cards.appendChild(e.node);
}

// ---------- rendering ----------

function renderChrome(node, d) {
  node.dataset.id = d.id;
  node.dataset.status = d.status;

  const path = node.querySelector(".status-path");
  if (path) path.setAttribute("d", STATUS_ICONS[d.status] || STATUS_ICONS.open);

  const title = node.querySelector(".issue-title");
  title.textContent = d.goal || "(no goal)";
  title.setAttribute("href", `#${d.id}`);

  const badges = node.querySelector(".issue-badges");
  badges.innerHTML = "";
  if (d.accepted_answer_id) {
    const acc = document.createElement("span");
    acc.className = "label label-accepted";
    acc.textContent = "✓ accepted";
    badges.appendChild(acc);
  }
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

function renderDetail(d) {
  // Write to modal slots
  if (modalState.id !== d.id) return; // stale render guard
  const dl = el.modalFields;
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
      highlight(pre);
    } else {
      dd.textContent = v;
    }
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  el.modalAnswers.innerHTML = "";
  for (const a of d.answers || []) {
    if (d.accepted_answer_id && d.accepted_answer_id === a.id) a.accepted = true;
    el.modalAnswers.appendChild(renderAnswer(a, d));
  }
}

function renderAnswer(a, parentRequest) {
  const div = document.createElement("div");
  div.className = "answer";
  div.dataset.id = a.id;
  if (a.accepted) div.classList.add("is-accepted");

  // Quality bar: upvote toggle + (asker-only) accept button + accepted pill
  const bar = document.createElement("div");
  bar.className = "ans-quality";

  const upBtn = document.createElement("button");
  upBtn.type = "button";
  upBtn.className = "btn btn-vote" + (a.voted_by_me ? " is-voted" : "");
  upBtn.title = state.actor ? `Toggle vote as ${state.actor}` : "Set 'Acting as' in the header to vote";
  upBtn.disabled = !state.actor;
  upBtn.innerHTML = `↑ <span class="vote-count">${a.votes || 0}</span>`;
  upBtn.addEventListener("click", () => toggleVote(a, parentRequest && parentRequest.id, div));
  bar.appendChild(upBtn);

  if (a.accepted) {
    const pill = document.createElement("span");
    pill.className = "label label-accepted";
    pill.textContent = "✓ accepted";
    bar.appendChild(pill);
  } else if (parentRequest && state.actor && state.actor === parentRequest.client_id) {
    const acceptBtn = document.createElement("button");
    acceptBtn.type = "button";
    acceptBtn.className = "btn btn-accept";
    acceptBtn.textContent = "Mark accepted";
    acceptBtn.addEventListener("click", () => markAccepted(parentRequest.id, a.id));
    bar.appendChild(acceptBtn);
  }
  div.appendChild(bar);

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
      highlight(pre);
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

  const title = node.querySelector(".issue-title");
  title.addEventListener("click", (e) => {
    e.preventDefault();
    openModal(d);
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
  if (modalState.id === rid) {
    if (!Array.isArray(entry.data.answers)) entry.data.answers = [ans];
    el.modalAnswers.appendChild(renderAnswer(ans, entry.data));
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
  applySort();
}

async function closeCard(id) {
  if (!confirm(`Close request #${id.slice(0, 7)}?`)) return;
  await fetchJson(`/api/requests/${id}/close`, { method: "POST" });
  if (modalState.id === id) closeModal();
}

async function toggleVote(answer, requestId, answerNode) {
  if (!state.actor) {
    alert("Set 'Acting as' (your client_id) in the header first.");
    return;
  }
  try {
    const r = await fetchJson(`/api/answers/${answer.id}/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voter: state.actor }),
    });
    answer.votes = r.votes;
    answer.voted_by_me = r.voted;
    if (answerNode) {
      const cnt = answerNode.querySelector(".vote-count");
      if (cnt) cnt.textContent = String(r.votes);
      const btn = answerNode.querySelector(".btn-vote");
      if (btn) btn.classList.toggle("is-voted", !!r.voted);
    }
    // Update parent card data so sort by upvoted reflects
    if (requestId) {
      const entry = state.cardsById.get(requestId);
      if (entry) {
        entry.data.top_votes = Math.max(entry.data.top_votes || 0, r.votes);
        if (state.sort === "upvoted") applySort();
      }
    }
  } catch (e) {
    console.warn("vote failed", e);
    alert(`Vote failed: ${e.message}`);
  }
}

async function markAccepted(rid, aid) {
  if (!state.actor) {
    alert("Set 'Acting as' (your client_id, must match request author) in the header.");
    return;
  }
  if (!confirm(`Mark answer #${aid.slice(0, 7)} as the accepted answer for request #${rid.slice(0, 7)}?`)) return;
  try {
    await fetchJson(`/api/requests/${rid}/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_id: aid, client_id: state.actor }),
    });
    // SSE will deliver request.accepted; UI re-renders from there.
  } catch (e) {
    if (String(e.message) === "403") {
      alert("Only the asker (matching client_id) can accept an answer.");
    } else {
      alert(`Accept failed: ${e.message}`);
    }
  }
}

async function deleteCard(id) {
  if (!confirm(`Permanently delete request #${id.slice(0, 7)}? This cannot be undone.`)) return;
  await fetchJson(`/api/requests/${id}`, { method: "DELETE" });
  if (modalState.id === id) closeModal();
}

// ---------- modal ----------

function openModal(d) {
  modalState.id = d.id;
  el.modal.dataset.status = d.status;
  if (el.modalStatus) {
    const path = el.modalStatus.querySelector(".status-path");
    if (path) path.setAttribute("d", STATUS_ICONS[d.status] || STATUS_ICONS.open);
  }
  el.modalId.textContent = `#${d.id.slice(0, 7)}`;
  el.modalGoal.textContent = d.goal || "(no goal)";
  el.modalMeta.innerHTML = "";
  const meta = document.createElement("span");
  meta.innerHTML = `<b>${escapeHtml(d.client_id || "?")}</b> · ${escapeHtml(d.model || "")} · opened ${escapeHtml(fmtRel(d.created_at))} · ${d.answer_count || 0} answers`;
  el.modalMeta.appendChild(meta);
  if (d.accepted_answer_id) {
    const pill = document.createElement("span");
    pill.className = "label label-accepted";
    pill.textContent = "✓ accepted";
    el.modalMeta.appendChild(pill);
  }
  renderDetail(d);
  el.modalRoot.hidden = false;
  document.body.classList.add("modal-open");
  setHash(d.id);
  fetchJson(`/api/requests/${d.id}`).then((fresh) => {
    if (modalState.id !== d.id) return;
    Object.assign(d, fresh);
    renderDetail(d);
    const span = el.modalMeta.querySelector("span");
    if (span) {
      span.innerHTML = `<b>${escapeHtml(d.client_id || "?")}</b> · ${escapeHtml(d.model || "")} · opened ${escapeHtml(fmtRel(d.created_at))} · ${d.answer_count || 0} answers`;
    }
  }).catch((e) => console.warn("detail fetch failed", e));
}

function closeModal() {
  if (!el.modalRoot || el.modalRoot.hidden) return;
  el.modalRoot.hidden = true;
  document.body.classList.remove("modal-open");
  modalState.id = null;
  clearHash();
}

if (el.modalCloseBtn) el.modalCloseBtn.addEventListener("click", () => closeModal());
if (el.modalCloseReq) el.modalCloseReq.addEventListener("click", () => {
  if (modalState.id) closeCard(modalState.id);
});
if (el.modalDeleteReq) el.modalDeleteReq.addEventListener("click", () => {
  if (modalState.id) deleteCard(modalState.id);
});
if (el.modalBackdrop) el.modalBackdrop.addEventListener("click", () => closeModal());
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && el.modalRoot && !el.modalRoot.hidden) {
    closeModal();
    e.preventDefault();
  }
}, true);

// ---------- permalink ----------

function setHash(id) {
  if (location.hash !== `#${id}`) history.replaceState(null, "", `#${id}`);
}
function clearHash() {
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
}

function jumpToHash() {
  const id = (location.hash || "").replace(/^#/, "");
  if (!id) return;
  const entry = state.cardsById.get(id);
  if (!entry) return;
  if (entry.node.style.display === "none") {
    el.tabs.forEach((b) => b.classList.toggle("is-active", b.dataset.status === "all"));
    state.filter.status = "all";
    applyFilterAll();
  }
  entry.node.scrollIntoView({ behavior: "smooth", block: "center" });
  focusRow(entry);
  if (modalState.id !== id) openModal(entry.data);
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
    applySort();
  });
  es.addEventListener("answer.created", (ev) => {
    const a = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    bumpAnswerCount(a.request_id, a);
    if (state.sort === "answered" || state.sort === "active") applySort();
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
  es.addEventListener("request.accepted", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    const entry = state.cardsById.get(d.request_id);
    if (!entry) return;
    entry.data.accepted_answer_id = d.accepted_answer_id;
    if (Array.isArray(entry.data.answers)) {
      for (const a of entry.data.answers) a.accepted = (a.id === d.accepted_answer_id);
    }
    renderChrome(entry.node, entry.data);
    if (modalState.id === d.request_id) renderDetail(entry.data);
  });
  es.addEventListener("answer.vote", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    const entry = state.cardsById.get(d.request_id);
    if (!entry) return;
    if (Array.isArray(entry.data.answers)) {
      for (const a of entry.data.answers) {
        if (a.id === d.answer_id) a.votes = d.votes;
      }
    }
    entry.data.top_votes = Math.max(entry.data.top_votes || 0, d.votes);
    if (modalState.id === d.request_id) {
      const ansNode = el.modalAnswers.querySelector(`.answer[data-id="${d.answer_id}"]`);
      if (ansNode) {
        const cnt = ansNode.querySelector(".vote-count");
        if (cnt) cnt.textContent = String(d.votes);
      }
    }
    if (state.sort === "upvoted") applySort();
  });
  es.addEventListener("replay-gap", (ev) => {
    console.warn("SSE replay-gap, refetching", ev.data);
    state.lastEventId = 0;
    state.cardsById.clear();
    el.cards.innerHTML = "";
    loadInitial();
  });
}

// ---------- keyboard navigation ----------

function visibleCards() {
  return [...state.cardsById.values()].filter(c => c.node.style.display !== "none");
}

function focusRow(entry) {
  for (const c of state.cardsById.values()) c.node.classList.remove("is-focused");
  if (!entry) { state.focusedId = null; return; }
  entry.node.classList.add("is-focused");
  state.focusedId = entry.data.id;
}

function focusedEntry() {
  return state.focusedId ? state.cardsById.get(state.focusedId) : null;
}

function focusOffset(delta) {
  const list = visibleCards();
  if (!list.length) return;
  let idx = list.findIndex(c => c.data.id === state.focusedId);
  if (idx < 0) idx = delta > 0 ? -1 : list.length;
  const next = list[Math.max(0, Math.min(list.length - 1, idx + delta))];
  if (!next) return;
  focusRow(next);
  next.node.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target;
  const tag = t && t.tagName;
  const inField = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

  if (e.key === "Escape") {
    if (document.activeElement === el.filterSearch) {
      el.filterSearch.value = "";
      el.filterSearch.dispatchEvent(new Event("input"));
      el.filterSearch.blur();
      e.preventDefault();
      return;
    }
    return;
  }
  if (inField) return;

  if (e.key === "/") {
    el.filterSearch.focus();
    e.preventDefault();
    return;
  }
  if (e.key === "j") { focusOffset(1); e.preventDefault(); return; }
  if (e.key === "k") { focusOffset(-1); e.preventDefault(); return; }
  if (e.key === "e" || e.key === "Enter") {
    const entry = focusedEntry();
    if (!entry) return;
    if (modalState.id === entry.data.id) closeModal();
    else openModal(entry.data);
    e.preventDefault();
    return;
  }
  if (e.key === "c") {
    const entry = focusedEntry();
    if (!entry) return;
    closeCard(entry.data.id);
    e.preventDefault();
    return;
  }
});

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

if (el.sortSelect) {
  el.sortSelect.addEventListener("change", (e) => {
    const v = e.target.value;
    if (!VALID_SORTS.includes(v)) return;
    state.sort = v;
    localStorage.setItem(SORT_KEY, v);
    applySort();
  });
}

if (el.actorInput) {
  el.actorInput.addEventListener("change", (e) => {
    state.actor = e.target.value.trim();
    localStorage.setItem(ACTOR_KEY, state.actor);
    if (modalState.id) {
      const entry = state.cardsById.get(modalState.id);
      if (entry) renderDetail(entry.data);
    }
  });
}

window.addEventListener("hashchange", jumpToHash);

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
    if (location.hash) setTimeout(jumpToHash, 50);
  } catch (e) {
    console.error("Dashboard init failed", e);
    setLive("disconnected", "offline");
  }
})();
