/* SI-KUR — utilitas bersama frontend (fetch API, format, komponen kecil) */
const API = {
  token() { return localStorage.getItem("sikur_token"); },
  user() { try { return JSON.parse(localStorage.getItem("sikur_user") || "null"); } catch { return null; } },
  async req(method, url, body) {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + (API.token() || "") },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401 && !url.includes("/auth/login")) { API.logoutLocal(); location.href = "/login.html"; throw new Error("Sesi berakhir"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let msg = data.detail;
      if (Array.isArray(msg)) msg = msg.map(d => (d.loc || []).slice(-1)[0] + ": " + d.msg).join("; ");
      throw new Error(msg || res.statusText);
    }
    return data;
  },
  get(u) { return API.req("GET", u); },
  post(u, b = {}) { return API.req("POST", u, b); },
  put(u, b = {}) { return API.req("PUT", u, b); },
  logoutLocal() { localStorage.removeItem("sikur_token"); localStorage.removeItem("sikur_user"); },
  async logout() { try { await API.post("/api/auth/logout"); } catch (e) {} API.logoutLocal(); location.href = "/login.html"; },
};

const fmt = {
  rp(x) { return "Rp " + Math.round(Number(x || 0)).toLocaleString("id-ID"); },
  jt(x) {
    const v = Number(x || 0) / 1e6;
    if (Math.abs(v) >= 1000) return "Rp " + (v / 1000).toLocaleString("id-ID", { maximumFractionDigits: 2 }) + " M";
    return "Rp " + v.toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " jt";
  },
  tgl(s) {
    if (!s) return "-";
    const d = new Date(s + "T00:00:00");
    return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
  },
  pct(a, b) { return b ? (a / b * 100) : 0; },
};

const STATUS = {
  AKTIF: { label: "Lancar", cls: "hijau" },
  PENGAWASAN: { label: "Dalam Pengawasan", cls: "kuning" },
  MACET: { label: "Macet (NPL)", cls: "merah" },
  LUNAS: { label: "Lunas", cls: "biru" },
  MENUNGGU: { label: "Menunggu Pencairan", cls: "abu" },
  DITOLAK: { label: "Ditolak/Batal", cls: "abu" },
};
function badge(status) {
  const s = STATUS[status] || { label: status || "-", cls: "abu" };
  return `<span class="badge b-${s.cls}">${s.label}</span>`;
}
function rowCls(status) { return "row-" + ((STATUS[status] || {}).cls || "abu"); }

const PENCAIRAN_STATUS = {
  DISETUJUI: ["Disetujui", "hijau"], DITUNDA_DANA_KURANG: ["Ditunda: dana kurang", "kuning"],
  DITUNDA_UNSAFE: ["Ditunda: UNSAFE", "merah"], DITOLAK_MELEBIHI_PLAFON: ["Ditolak: > plafon", "abu"],
  DIBATALKAN: ["Dibatalkan", "abu"], BARU: ["Baru", "abu"],
};
function badgeP(st) { const [l, c] = PENCAIRAN_STATUS[st] || [st, "abu"]; return `<span class="badge b-${c}">${l}</span>`; }

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }

function toast(msg, type = "") {
  let box = $(".toast-box");
  if (!box) { box = document.createElement("div"); box.className = "toast-box"; document.body.appendChild(box); }
  const t = document.createElement("div");
  t.className = "toast " + type; t.textContent = msg; box.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

function modal(html, onMount) {
  let bg = $("#modal-bg");
  if (!bg) { bg = document.createElement("div"); bg.id = "modal-bg"; bg.className = "modal-bg"; document.body.appendChild(bg); }
  bg.innerHTML = `<div class="modal">${html}</div>`;
  bg.classList.add("show");
  bg.onclick = e => { if (e.target === bg) closeModal(); };
  $$("[data-close]", bg).forEach(b => b.onclick = closeModal);
  if (onMount) onMount(bg);
}
function closeModal() { const bg = $("#modal-bg"); if (bg) bg.classList.remove("show"); }

function parseRp(v) { return Number(String(v).replace(/[^\d]/g, "")) || 0; }
function bindRupiahInput(input) {
  input.addEventListener("input", () => {
    const n = parseRp(input.value);
    input.value = n ? n.toLocaleString("id-ID") : "";
  });
}

function seqHtml(seq, names, hl) {
  if (!seq || !seq.length) return '<span class="muted">— tidak ada urutan aman —</span>';
  return '<div class="seq">' + seq.map((p, i) =>
    `${i ? '<span class="arrow">→</span>' : ""}<span class="node ${p === hl ? "hl" : ""}" title="Kredit #${p}">${esc(names[p] || "#" + p)}</span>`
  ).join("") + "</div>";
}

function requireRole(roles) {
  const u = API.user();
  if (!API.token() || !u || !roles.includes(u.peran)) { location.href = "/login.html"; return null; }
  return u;
}
