// ---- Config (stored in localStorage) ----------------------------------
const cfg = {
  get owner() { return localStorage.getItem("gh_owner") || ""; },
  get repo() { return localStorage.getItem("gh_repo") || ""; },
  get branch() { return localStorage.getItem("gh_branch") || "main"; },
  get token() { return localStorage.getItem("gh_token") || ""; },
  get configured() { return this.owner && this.repo && this.token; },
};

const API_BASE = () => `https://api.github.com/repos/${cfg.owner}/${cfg.repo}`;
const RAW_BASE = () => `https://raw.githubusercontent.com/${cfg.owner}/${cfg.repo}/${cfg.branch}`;

let feed = [];
let ratedIds = new Set();
let activeSource = "all";

// ---- GitHub Contents API helpers ---------------------------------------

async function ghGetFile(path) {
  const res = await fetch(`${API_BASE()}/contents/${path}?ref=${cfg.branch}`, {
    headers: { Authorization: `Bearer ${cfg.token}`, Accept: "application/vnd.github+json" },
  });
  if (res.status === 404) return { sha: null, content: null };
  if (!res.ok) throw new Error(`GitHub GET ${path} failed: ${res.status}`);
  const data = await res.json();
  const content = decodeURIComponent(escape(atob(data.content.replace(/\n/g, ""))));
  return { sha: data.sha, content };
}

async function ghPutFile(path, contentStr, sha, message) {
  const encoded = btoa(unescape(encodeURIComponent(contentStr)));
  const body = { message, content: encoded, branch: cfg.branch };
  if (sha) body.sha = sha;
  const res = await fetch(`${API_BASE()}/contents/${path}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`GitHub PUT ${path} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function submitRating(id, rating) {
  // 1 = interesting, -1 = not interesting, 0 = dismissed/neutral
  const { sha, content } = await ghGetFile("data/ratings.json");
  const ratings = content ? JSON.parse(content) : [];
  ratings.push({ id, rating, ts: new Date().toISOString() });
  await ghPutFile("data/ratings.json", JSON.stringify(ratings, null, 2), sha,
    `Rate ${id}: ${rating > 0 ? "up" : rating < 0 ? "down" : "skip"}`);
  ratedIds.add(id);
}

async function uploadBib(file) {
  const text = await file.text();
  const { sha } = await ghGetFile("data/seed.bib");
  await ghPutFile("data/seed.bib", text, sha, "Update seed.bib from app");
}

// ---- Feed loading & rendering ------------------------------------------

async function loadFeed() {
  const emptyState = document.getElementById("emptyState");
  emptyState.textContent = "Loading your feed…";
  emptyState.style.display = "block";
  try {
    const bust = Date.now();
    const [feedRes, ratingsRes] = await Promise.all([
      fetch(`${RAW_BASE()}/data/feed.json?_=${bust}`),
      fetch(`${RAW_BASE()}/data/ratings.json?_=${bust}`),
    ]);
    feed = feedRes.ok ? await feedRes.json() : [];
    const ratings = ratingsRes.ok ? await ratingsRes.json() : [];
    ratedIds = new Set(ratings.map(r => r.id));
  } catch (e) {
    emptyState.textContent = "Couldn't load feed. Check Settings and your connection.";
    console.error(e);
    return;
  }
  render();
}

function render() {
  const container = document.getElementById("feed");
  const emptyState = document.getElementById("emptyState");
  container.querySelectorAll(".card").forEach(el => el.remove());

  const visible = feed.filter(p => !ratedIds.has(p.id) &&
    (activeSource === "all" || p.source === activeSource));

  if (visible.length === 0) {
    emptyState.style.display = "block";
    emptyState.textContent = feed.length === 0
      ? "No papers yet — check back after the first daily run, or trigger it manually from the Actions tab."
      : "You're all caught up! 🎉";
    return;
  }
  emptyState.style.display = "none";

  const tmpl = document.getElementById("cardTemplate");
  for (const paper of visible) {
    const node = tmpl.content.cloneNode(true);
    const card = node.querySelector(".card");
    card.dataset.id = paper.id;
    node.querySelector(".badge").textContent = paper.source;
    node.querySelector(".score").textContent = `match ${Math.round((paper.score ?? 0.5) * 100)}%`;
    node.querySelector(".title").textContent = paper.title;
    const authors = (paper.authors || []).slice(0, 3).join(", ") +
      ((paper.authors || []).length > 3 ? " et al." : "");
    node.querySelector(".meta").textContent = [authors, paper.date].filter(Boolean).join(" · ");
    const abs = node.querySelector(".abstract");
    abs.textContent = paper.abstract || "(no abstract available)";
    abs.addEventListener("click", () => abs.classList.toggle("expanded"));
    node.querySelector(".open").href = paper.url;

    node.querySelector(".up").addEventListener("click", async (e) => {
      e.target.disabled = true;
      await submitRating(paper.id, 1).catch(console.error);
      card.remove();
      maybeShowEmpty();
    });
    node.querySelector(".down").addEventListener("click", async (e) => {
      e.target.disabled = true;
      await submitRating(paper.id, -1).catch(console.error);
      card.remove();
      maybeShowEmpty();
    });

    container.appendChild(node);
  }
}

function maybeShowEmpty() {
  if (document.querySelectorAll(".card").length === 0) render();
}

// ---- Settings modal ------------------------------------------------------

const modal = document.getElementById("settingsModal");

function openSettings() {
  document.getElementById("ghOwner").value = cfg.owner;
  document.getElementById("ghRepo").value = cfg.repo;
  document.getElementById("ghBranch").value = cfg.branch;
  document.getElementById("ghToken").value = cfg.token;
  document.getElementById("bibStatus").textContent = "";
  modal.showModal();
}

document.getElementById("settingsBtn").addEventListener("click", openSettings);
document.getElementById("closeSettingsBtn").addEventListener("click", () => modal.close());
document.getElementById("refreshBtn").addEventListener("click", loadFeed);

document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
  localStorage.setItem("gh_owner", document.getElementById("ghOwner").value.trim());
  localStorage.setItem("gh_repo", document.getElementById("ghRepo").value.trim());
  localStorage.setItem("gh_branch", document.getElementById("ghBranch").value.trim() || "main");
  localStorage.setItem("gh_token", document.getElementById("ghToken").value.trim());

  const bibInput = document.getElementById("bibFile");
  const status = document.getElementById("bibStatus");
  if (bibInput.files.length > 0) {
    status.textContent = "Uploading .bib…";
    try {
      await uploadBib(bibInput.files[0]);
      status.textContent = "Uploaded! Your preference vector will update shortly (check the Actions tab).";
    } catch (e) {
      status.textContent = "Upload failed — check your token has write access.";
      console.error(e);
      return;
    }
  }
  modal.close();
  loadFeed();
});

document.getElementById("sourceFilters").addEventListener("click", (e) => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
  btn.classList.add("active");
  activeSource = btn.dataset.source;
  render();
});

// ---- Boot -----------------------------------------------------------------

if (!cfg.configured) {
  openSettings();
} else {
  loadFeed();
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
