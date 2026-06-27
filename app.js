// ── Tools Hub: データ駆動の静的サイト ──────────────────────────────
let tools = [];
let activeTag = null;
let query = "";

const grid = document.getElementById("tool-grid");
const empty = document.getElementById("empty");
const searchInput = document.getElementById("search");
const tagFilters = document.getElementById("tag-filters");

// ── 読み込み ──
async function load() {
  try {
    const res = await fetch("tools.json");
    tools = await res.json();
  } catch (e) {
    grid.innerHTML = `<p class="empty">tools.json を読み込めませんでした。</p>`;
    return;
  }
  renderTags();
  render();
}

// ── タグフィルタ生成 ──
function renderTags() {
  const allTags = [...new Set(tools.flatMap(t => t.tags || []))].sort();
  tagFilters.innerHTML = "";
  allTags.forEach(tag => {
    const chip = document.createElement("button");
    chip.className = "tag-chip";
    chip.textContent = tag;
    chip.onclick = () => {
      activeTag = activeTag === tag ? null : tag;
      renderTags();
      render();
    };
    if (tag === activeTag) chip.classList.add("active");
    tagFilters.appendChild(chip);
  });
}

// ── カード描画 ──
function render() {
  const q = query.trim().toLowerCase();
  const filtered = tools.filter(t => {
    const matchTag = !activeTag || (t.tags || []).includes(activeTag);
    const haystack = `${t.title} ${t.desc} ${(t.tags || []).join(" ")}`.toLowerCase();
    const matchQuery = !q || haystack.includes(q);
    return matchTag && matchQuery;
  });

  grid.innerHTML = "";
  empty.hidden = filtered.length > 0;

  filtered.forEach(t => {
    const a = document.createElement("a");
    a.className = "card";
    a.href = t.url || "#";
    if (t.url && t.url !== "#") { a.target = "_blank"; a.rel = "noopener"; }
    a.innerHTML = `
      <div class="card-icon">${t.icon || "🔧"}</div>
      <h2 class="card-title">${escapeHtml(t.title)}</h2>
      <p class="card-desc">${escapeHtml(t.desc)}</p>
      <div class="card-tags">
        ${(t.tags || []).map(tag => `<span class="card-tag">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="card-cta">${escapeHtml(t.cta || "開く →")}</div>
    `;
    grid.appendChild(a);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── 検索 ──
searchInput.addEventListener("input", e => { query = e.target.value; render(); });

// ── テーマ切替（localStorage 永続化）──
const themeToggle = document.getElementById("theme-toggle");
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
  localStorage.setItem("theme", theme);
}
themeToggle.onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme");
  applyTheme(cur === "dark" ? "light" : "dark");
};
applyTheme(
  localStorage.getItem("theme") ||
  (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
);

// ── 初期化 ──
document.getElementById("year").textContent = new Date().getFullYear();
load();
