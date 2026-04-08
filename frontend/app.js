/**
 * YC Company Research — Frontend
 *
 * Fetches from GET /companies (with optional ?industry= and ?q= params)
 * and renders company cards. All filtering is server-side.
 */

// Industry → Tailwind color class mapping
const INDUSTRY_COLORS = {
  "FinTech":          "bg-emerald-100 text-emerald-800",
  "HealthTech":       "bg-blue-100 text-blue-800",
  "AI/ML":            "bg-purple-100 text-purple-800",
  "DevTools":         "bg-yellow-100 text-yellow-800",
  "Enterprise SaaS":  "bg-indigo-100 text-indigo-800",
  "E-Commerce":       "bg-pink-100 text-pink-800",
  "EdTech":           "bg-cyan-100 text-cyan-800",
  "Defense/Security": "bg-red-100 text-red-800",
  "Robotics/Hardware":"bg-orange-100 text-orange-800",
  "Biotech":          "bg-teal-100 text-teal-800",
  "Media/Entertainment":"bg-fuchsia-100 text-fuchsia-800",
  "Marketplace":      "bg-lime-100 text-lime-800",
  "Other":            "bg-gray-100 text-gray-600",
};

const grid         = document.getElementById("grid");
const loading      = document.getElementById("loading");
const emptyState   = document.getElementById("empty-state");
const errorState   = document.getElementById("error-state");
const errorMsg     = document.getElementById("error-msg");
const stats        = document.getElementById("stats");
const searchInput  = document.getElementById("search-input");
const industrySelect = document.getElementById("industry-select");
const clearBtn     = document.getElementById("clear-btn");

let debounceTimer = null;

// ---- Rendering ----

function industryBadge(industry) {
  if (!industry) return "";
  const cls = INDUSTRY_COLORS[industry] || "bg-gray-100 text-gray-600";
  return `<span class="industry-badge ${cls}">${escapeHtml(industry)}</span>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderCard(c) {
  const websiteLink = c.website
    ? `<a href="${escapeHtml(c.website)}" target="_blank" rel="noopener"
          class="text-xs text-orange-500 hover:underline truncate block mt-2"
        >${escapeHtml(c.website.replace(/^https?:\/\//, ""))}</a>`
    : "";

  return `
    <article class="card bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex flex-col gap-2">
      <div class="flex items-start justify-between gap-2">
        <h2 class="font-semibold text-gray-900 text-sm leading-tight">${escapeHtml(c.company_name)}</h2>
        ${industryBadge(c.industry)}
      </div>
      ${c.business_model
        ? `<p class="text-xs text-gray-500 font-medium">${escapeHtml(c.business_model)}</p>`
        : ""}
      <p class="text-xs text-gray-600 leading-relaxed flex-1 line-clamp-3">
        ${escapeHtml(c.summary || c.description || "")}
      </p>
      ${c.use_case
        ? `<p class="text-xs text-indigo-600 italic leading-snug line-clamp-2">${escapeHtml(c.use_case)}</p>`
        : ""}
      ${websiteLink}
    </article>`;
}

function setUI(state) {
  loading.classList.toggle("hidden",     state !== "loading");
  emptyState.classList.toggle("hidden",  state !== "empty");
  errorState.classList.toggle("hidden",  state !== "error");
}

function updateStats(count, total) {
  if (total === 0) { stats.textContent = ""; return; }
  stats.textContent = count === total
    ? `${total} companies`
    : `${count} of ${total} companies`;
}

// ---- Data fetching ----

async function fetchCompanies(industry, q) {
  const params = new URLSearchParams();
  if (industry) params.set("industry", industry);
  if (q)        params.set("q", q);
  const url = `/companies/${params.toString() ? "?" + params : ""}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

async function loadAndRender() {
  const industry = industrySelect.value;
  const q        = searchInput.value.trim();
  const hasFilt  = industry || q;

  clearBtn.classList.toggle("hidden", !hasFilt);
  setUI("loading");
  grid.innerHTML = "";

  try {
    const companies = await fetchCompanies(industry, q);
    setUI(companies.length === 0 ? "empty" : "done");
    grid.innerHTML = companies.map(renderCard).join("");
    updateStats(companies.length, companies.length);
  } catch (err) {
    setUI("error");
    errorMsg.textContent = `Failed to load companies: ${err.message}`;
  }
}

// ---- Industry dropdown population ----

async function populateIndustries() {
  try {
    const all = await fetchCompanies("", "");
    const industries = [...new Set(all.map(c => c.industry).filter(Boolean))].sort();
    industries.forEach(ind => {
      const opt = document.createElement("option");
      opt.value = ind;
      opt.textContent = ind;
      industrySelect.appendChild(opt);
    });
  } catch {
    // Non-fatal — dropdown just won't have options
  }
}

// ---- Event handlers ----

industrySelect.addEventListener("change", loadAndRender);

searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(loadAndRender, 300);
});

clearBtn.addEventListener("click", () => {
  searchInput.value = "";
  industrySelect.value = "";
  loadAndRender();
});

// ---- Bootstrap ----

(async () => {
  await populateIndustries();
  await loadAndRender();
})();
