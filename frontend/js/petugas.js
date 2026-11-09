/* SI-KUR — Dashboard Petugas / Admin (SPA sederhana berbasis hash) */
const ME = requireRole(["ADMIN", "PETUGAS"]);
const view = $("#view");
const TITLES = {
  ringkasan: "Ringkasan Portofolio", bankers: "Banker's Algorithm — Uji Keamanan Dana",
  watchlist: "Slot Pengawasan Intensif (LFU)", notifikasi: "Notifikasi & Eskalasi",
  pengajuan: "Pengajuan Kredit & Pencairan", debitur: "Data Debitur", arsip: "Arsip Kredit (Buku Induk)",
  simulasi: "Timer Otomatis & Simulasi Waktu", pengaturan: "Pengaturan Aturan Risiko & Log",
};
if (ME) $("#user-chip").textContent = `${ME.nama} · ${ME.peran}`;

async function refreshHeader() {
  try {
    const d = await API.get("/api/sistem");
    $("#tgl-sistem").textContent = fmt.tgl(d.parameter.tanggal_sistem) + (d.parameter.auto_timer_aktif ? " ⏵" : "");
    const n = await API.get("/api/notifikasi");
    const unread = n.filter(x => !x.dibaca).length;
    const c = $("#notif-count"); c.hidden = !unread; c.textContent = unread;
  } catch (e) { /* abaikan */ }
}

const ROUTES = {};
async function router() {
  const [page, arg] = (location.hash.slice(1) || "ringkasan").split("/");
  $$("#nav a").forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + page));
  $("#page-title").textContent = TITLES[page] || "SI-KUR";
  view.innerHTML = '<div class="empty">Memuat…</div>';
  try { await (ROUTES[page] || ROUTES.ringkasan)(arg); }
  catch (e) { view.innerHTML = `<div class="alert bad">Gagal memuat: ${esc(e.message)}</div>`; }
  refreshHeader();
}
window.addEventListener("hashchange", router);

/* ====================================================== RINGKASAN */
ROUTES.ringkasan = async () => {
  const d = await API.get("/api/dashboard");
  const st = d.status_kredit, dn = d.dana;
  const aktif = (st.AKTIF || 0), awas = (st.PENGAWASAN || 0), macet = (st.MACET || 0), lunas = (st.LUNAS || 0);
  const names = {}; (await API.get("/api/bankers/state")).proses.forEach(p => names[p.kredit_id] = p.nama.split(" ")[0]);
  const pAvail = fmt.pct(dn.available, dn.pagu), pAlloc = fmt.pct(d.banker.total_allocation, dn.pagu),
        pLoss = fmt.pct(dn.total_kerugian_npl, dn.pagu);
  // tren insiden per bulan
  const bulan = {}; d.tren_insiden.forEach(t => { (bulan[t.bulan] = bulan[t.bulan] || {})[t.jenis] = t.n; });
  const keys = Object.keys(bulan).slice(-10);
  const maxN = Math.max(1, ...keys.map(k => Object.values(bulan[k]).reduce((a, b) => a + b, 0)));
  const JC = { TELAT_BAYAR: "#eab308", TUNGGAKAN_BERLANJUT: "#dc2626", USAHA_MENURUN: "#1769aa", LAINNYA: "#98a2b3" };

  view.innerHTML = `
  <div class="safe-banner ${d.safe ? "safe" : "unsafe"}">
    <div class="big">${d.safe ? "✔ SAFE STATE" : "✖ UNSAFE STATE"}</div>
    <div style="flex:1">
      <div class="small">${d.safe ? "Seluruh debitur aktif secara teoretis dapat dilunasi tanpa dana KUR kolaps. Safe sequence:" :
        "Sistem berada dalam state tidak aman!"}</div>
      ${seqHtml(d.safe_sequence, names)}
    </div>
    <a class="btn sm" href="#bankers">Detail matriks →</a>
  </div>
  <div class="grid g4">
    <div class="kpi accent"><div class="label">Pagu Dana KUR</div><div class="value">${fmt.jt(dn.pagu)}</div><div class="sub">Total dana yang dikelola unit</div></div>
    <div class="kpi ok"><div class="label">Available</div><div class="value">${fmt.jt(dn.available)}</div><div class="sub">${pAvail.toFixed(1)}% dari pagu siap dicairkan</div></div>
    <div class="kpi warn"><div class="label">Allocation (Outstanding)</div><div class="value">${fmt.jt(d.banker.total_allocation)}</div><div class="sub">Need tersisa ${fmt.jt(d.banker.total_need)}</div></div>
    <div class="kpi bad"><div class="label">Rasio NPL</div><div class="value">${d.npl_ratio}%</div><div class="sub">Kerugian bersih ${fmt.jt(dn.total_kerugian_npl)}</div></div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-head"><h2>Komposisi Dana KUR</h2><div class="spacer"></div>
      <span class="small ${d.invariant_ok ? "" : "b-merah badge"}">${d.invariant_ok ? "✔ Konservasi dana valid: Available + Allocation + Kerugian = Pagu" : "Invariant dana TIDAK valid"}</span></div>
    <div class="fund-bar">
      <span style="width:${pAlloc}%;background:#1769aa">Allocation ${pAlloc.toFixed(1)}%</span>
      <span style="width:${pAvail}%;background:#15803d">Available ${pAvail.toFixed(1)}%</span>
      <span style="width:${pLoss}%;background:#b91c1c" title="Kerugian NPL">${pLoss > 3 ? "NPL " + pLoss.toFixed(1) + "%" : ""}</span>
    </div>
    <div class="legend"><span><i style="background:#1769aa"></i>Sudah dicairkan (Allocation)</span><span><i style="background:#15803d"></i>Sisa dana (Available)</span><span><i style="background:#b91c1c"></i>Kerugian NPL setelah klaim penjaminan</span>
      <span>Klaim penjaminan diterima: <b>${fmt.jt(dn.total_klaim_penjaminan)}</b></span><span>Bunga diterima: <b>${fmt.jt(dn.total_bunga_diterima)}</b></span></div>
  </div>
  <div class="grid g4">
    <a class="kpi ok" href="#debitur" onclick="sessionStorage.f='AKTIF'"><div class="label">🟢 Lancar</div><div class="value">${aktif}</div><div class="sub">debitur</div></a>
    <a class="kpi warn" href="#debitur" onclick="sessionStorage.f='PENGAWASAN'"><div class="label">🟡 Dalam Pengawasan</div><div class="value">${awas}</div><div class="sub">Outstanding ${fmt.jt(d.outstanding_pengawasan)}</div></a>
    <a class="kpi bad" href="#debitur" onclick="sessionStorage.f='MACET'"><div class="label">🔴 Macet (NPL)</div><div class="value">${macet}</div><div class="sub">alokasi telah dicabut</div></a>
    <a class="kpi accent" href="#arsip"><div class="label">🔵 Lunas</div><div class="value">${lunas}</div><div class="sub">diarsipkan</div></a>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card">
      <div class="card-head"><h2>Antrean Pencairan Ditunda</h2><div class="spacer"></div><a class="small" href="#pengajuan">Kelola →</a></div>
      ${d.antrean.length ? `<table><tr><th>Debitur</th><th class="num">Jumlah</th><th>Alasan</th></tr>
        ${d.antrean.map(a => `<tr><td>${esc(a.nama)}<div class="small muted">sejak ${fmt.tgl(a.tanggal_ajuan)}</div></td><td class="num">${fmt.jt(a.jumlah)}</td><td>${badgeP(a.status)}</td></tr>`).join("")}</table>`
        : '<div class="empty">Tidak ada antrean.</div>'}
      <p class="hint">Antrean diproses ulang otomatis (FIFO) setiap ada dana kembali dari angsuran, pelunasan, atau klaim penjaminan.</p>
    </div>
    <div class="card">
      <div class="card-head"><h2>Slot Pengawasan Intensif</h2><div class="spacer"></div><span class="small muted">${d.watchlist.terisi}/${d.watchlist.kapasitas} terisi</span><a class="small" href="#watchlist">Detail →</a></div>
      <table><tr><th>Debitur</th><th class="num">Frekuensi</th><th>Status</th></tr>
      ${d.watchlist.slot.map(s => `<tr><td><a href="#debitur/${s.id}">${esc(s.nama)}</a>${s.id === d.watchlist.calon_evict ? ' <span class="badge b-merah">calon evict</span>' : ""}</td><td class="num"><b>${s.frekuensi}</b></td><td>${badge(s.status)}</td></tr>`).join("") || '<tr><td colspan=3 class="empty">Kosong</td></tr>'}
      </table>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>Tren Insiden Risiko per Bulan</h2></div>
    <div class="chart-bars">
      ${keys.map(k => { const tot = Object.values(bulan[k]).reduce((a, b) => a + b, 0);
        return `<div class="col"><span class="small"><b>${tot}</b></span><div class="stack" style="height:${tot / maxN * 100}%">
          ${Object.entries(bulan[k]).map(([j, n]) => `<span style="height:${n / tot * 100}%;background:${JC[j] || "#999"}" title="${j}: ${n}"></span>`).join("")}
        </div><span class="lbl">${k.slice(5)}/${k.slice(2, 4)}</span></div>`; }).join("")}
    </div>
    <div class="legend">${Object.entries(JC).map(([j, c]) => `<span><i style="background:${c}"></i>${j.replace(/_/g, " ").toLowerCase()}</span>`).join("")}</div>
  </div>`;
};

/* ====================================================== BANKER'S */
ROUTES.bankers = async () => {
  const s = await API.get("/api/bankers/state");
  const names = {}; s.proses.forEach(p => names[p.kredit_id] = p.nama.split(" ")[0]);
  const maxMax = Math.max(1, ...s.proses.map(p => p.max));
  view.innerHTML = `
  <div class="safe-banner ${s.safety.safe ? "safe" : "unsafe"}">
    <div class="big">${s.safety.safe ? "✔ SAFE" : "✖ UNSAFE"}</div>
    <div style="flex:1"><div class="small">Safe sequence (urutan debitur yang dapat melunasi satu per satu):</div>${seqHtml(s.safety.sequence, names)}</div>
  </div>
  <div class="grid g4">
    <div class="kpi ok"><div class="label">Available</div><div class="value">${fmt.jt(s.available)}</div><div class="sub mono">${fmt.rp(s.available)}</div></div>
    <div class="kpi accent"><div class="label">Σ Allocation</div><div class="value">${fmt.jt(s.total_allocation)}</div></div>
    <div class="kpi warn"><div class="label">Σ Need</div><div class="value">${fmt.jt(s.total_need)}</div><div class="sub">Klaim potensial yang belum dicairkan</div></div>
    <div class="kpi"><div class="label">Proses aktif</div><div class="value">${s.proses.length}</div><div class="sub">debitur di simulasi</div></div>
  </div>
  <div class="grid g-wide" style="margin-top:16px">
    <div class="card">
      <div class="card-head"><h2>Matriks Max · Allocation · Need</h2></div>
      <div class="table-wrap"><table>
        <tr><th>P</th><th>Debitur</th><th>Status</th><th class="num">Max</th><th class="num">Allocation</th><th class="num">Need</th><th>Proporsi</th></tr>
        ${s.proses.map(p => `<tr class="${rowCls(p.status)}"><td class="mono">K${p.kredit_id}</td><td><a href="#debitur/${p.debitur_id}">${esc(p.nama)}</a></td><td>${badge(p.status)}</td>
          <td class="num">${fmt.jt(p.max)}</td><td class="num">${fmt.jt(p.allocation)}</td><td class="num">${fmt.jt(p.need)}</td>
          <td><div class="bar" style="width:${Math.max(30, p.max / maxMax * 100)}%"><span class="alloc" style="width:${fmt.pct(p.allocation, p.max)}%"></span><span class="need" style="width:${fmt.pct(p.need, p.max)}%"></span></div></td></tr>`).join("")}
      </table></div>
      <div class="legend"><span><i style="background:#1769aa"></i>Allocation</span><span><i style="background:#b6d4ef"></i>Need = Max − Allocation</span></div>
    </div>
    <div>
      <div class="card">
        <div class="card-head"><h2>Simulasi "What-if" Pencairan</h2></div>
        <p class="small muted">Jalankan Resource-Request Algorithm tanpa menyimpan apa pun.</p>
        <label>Kredit / Debitur</label>
        <select id="sim-k">${s.proses.filter(p => p.status !== "PENGAWASAN").map(p => `<option value="${p.kredit_id}" data-need="${p.need}">K${p.kredit_id} · ${esc(p.nama)} (Need ${fmt.jt(p.need)})</option>`).join("")}</select>
        <label>Jumlah pencairan (Rp)</label>
        <input id="sim-j" inputmode="numeric" placeholder="mis. 50.000.000">
        <div class="toolbar" style="margin-top:10px">
          <button class="btn" id="sim-run">Uji keamanan</button>
          <button class="btn primary" id="sim-go">Ajukan sungguhan</button>
        </div>
        <div id="sim-out"></div>
      </div>
      <div class="card">
        <h3>Cara membaca</h3>
        <ol class="small" style="padding-left:18px;line-height:1.7;margin:0">
          <li><b>Request ≤ Need</b>? Jika tidak → ditolak (melebihi plafon).</li>
          <li><b>Request ≤ Available</b>? Jika tidak → ditunda (dana kurang).</li>
          <li>Pura-pura cairkan, lalu jalankan <b>Safety Algorithm</b>: cari debitur yang Need-nya ≤ Work, anggap lunas, Work += Allocation-nya.</li>
          <li>Semua debitur bisa "selesai" → <b>SAFE</b> → cair. Jika tidak → <b>UNSAFE</b> → ditunda.</li>
        </ol>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>Jejak Safety Algorithm (state saat ini)</h2></div>
    ${stepsTable(s.safety.steps, names)}
  </div>`;
  const inp = $("#sim-j"); bindRupiahInput(inp);
  $("#sim-run").onclick = async () => {
    try {
      const r = await API.post(`/api/bankers/simulasi/${$("#sim-k").value}`, { jumlah: parseRp(inp.value) });
      $("#sim-out").innerHTML = resultHtml(r, names, Number($("#sim-k").value));
    } catch (e) { $("#sim-out").innerHTML = `<div class="alert bad">${esc(e.message)}</div>`; }
  };
  $("#sim-go").onclick = async () => {
    try {
      const r = await API.post(`/api/kredit/${$("#sim-k").value}/pencairan`, { jumlah: parseRp(inp.value) });
      toast(r.message, r.granted ? "ok" : "bad");
      await ROUTES.bankers();
      $("#sim-out").innerHTML = resultHtml(r, names, r.kredit_id);
    } catch (e) { $("#sim-out").innerHTML = `<div class="alert bad">${esc(e.message)}</div>`; }
  };
};

function stepsTable(steps, names) {
  if (!steps.length) return '<div class="empty">Tidak ada langkah — tidak ada debitur yang dapat diselesaikan dengan Work saat ini.</div>';
  return `<div class="table-wrap"><table class="steps"><tr><th>#</th><th>Debitur selesai</th><th class="num">Work sebelum</th><th class="num">Need ≤ Work</th><th class="num">+ Allocation dikembalikan</th><th class="num">Work sesudah</th></tr>
  ${steps.map((st, i) => `<tr><td>${i + 1}</td><td>K${st.pid} · ${esc(names[st.pid] || "")}</td><td class="num">${fmt.jt(st.work_before[0])}</td><td class="num">${fmt.jt(st.need[0])}</td><td class="num">${fmt.jt(st.allocation[0])}</td><td class="num"><b>${fmt.jt(st.work_after[0])}</b></td></tr>`).join("")}
  </table></div>`;
}

function resultHtml(r, names, pid) {
  const cls = r.granted ? "ok" : r.status === "DITUNDA_UNSAFE" ? "bad" : "warn";
  let html = `<div class="alert ${cls}" style="margin-top:12px"><b>${badgeP(r.status)}</b><div style="margin-top:6px">${esc(r.message)}</div></div>`;
  if (r.safety) {
    html += `<div class="small"><b>${r.safety.safe ? "Safe sequence setelah pencairan:" : "Debitur yang bisa diselesaikan sebelum macet:"}</b></div>${seqHtml(r.safety.sequence, names, pid)}`;
    if (!r.safety.safe) html += `<div class="small" style="margin-top:6px">Tidak dapat diselesaikan: ${r.safety.stuck.map(p => "K" + p + " " + esc(names[p] || "")).join(", ")}</div>`;
  }
  return html;
}

/* ====================================================== WATCHLIST */
ROUTES.watchlist = async () => {
  const w = await API.get("/api/watchlist");
  const maxF = Math.max(5, ...w.slot.map(s => s.frekuensi));
  const kosong = Math.max(0, w.kapasitas - w.slot.length);
  view.innerHTML = `
  <div class="alert info">Kapasitas slot pengawasan intensif: <b>${w.kapasitas}</b>. Setiap insiden risiko (telat bayar melewati grace period, tunggakan berlanjut, laporan usaha menurun) menambah <b>frekuensi</b>. Saat slot penuh dan ada debitur baru berisiko, debitur dengan <b>frekuensi paling jarang</b> dikeluarkan (Least Frequently Used; seri → yang insidennya paling lama). Frekuensi turun 1 tiap 30 hari tanpa insiden (aging).</div>
  <div class="card">
    <div class="card-head"><h2>Slot Pengawasan</h2><div class="spacer"></div><span class="muted small">Urut dari frekuensi tertinggi</span></div>
    <div class="slots">
      ${w.slot.map((s, i) => `<div class="slot ${s.id === w.calon_evict ? "victim" : ""} ${s.frekuensi >= 5 ? "hot" : ""}">
        <span class="no">Slot ${i + 1}</span>
        ${badge(s.status)}
        <div class="nm"><a href="#debitur/${s.id}">${esc(s.nama)}</a></div>
        <div class="small muted">${esc(s.nama_usaha || "")}</div>
        <div class="freq">${s.frekuensi} <small>insiden</small></div>
        <div class="meter">${Array.from({ length: maxF }, (_, k) => `<i class="${k < s.frekuensi ? "on" : ""}"></i>`).join("")}</div>
        <div class="small muted">Tunggakan ${s.hari_tunggakan ?? 0} hari · masuk ${fmt.tgl(s.tanggal_masuk)}</div>
        <div class="small muted">Insiden terakhir ${fmt.tgl(s.insiden_terakhir)} · urutan evict #${s.posisi_evict}</div>
      </div>`).join("")}
      ${Array.from({ length: kosong }, () => '<div class="slot kosong">Slot kosong</div>').join("")}
    </div>
  </div>
  <div class="grid g2">
    <div class="card">
      <div class="card-head"><h2>Dalam Pengawasan, di luar slot intensif</h2></div>
      ${w.kandidat_luar_slot.length ? `<table><tr><th>Debitur</th><th class="num">Total insiden</th><th class="num">Tunggakan</th></tr>
      ${w.kandidat_luar_slot.map(k => `<tr class="row-kuning"><td><a href="#debitur/${k.id}">${esc(k.nama)}</a></td><td class="num">${k.jumlah_insiden}</td><td class="num">${k.hari_tunggakan} hr</td></tr>`).join("")}</table>`
        : '<div class="empty">Tidak ada — semua debitur pengawasan sudah di slot intensif.</div>'}
      <p class="hint">Debitur di sini tetap dipantau secara reguler (bukan intensif).</p>
    </div>
    <div class="card">
      <div class="card-head"><h2>Log Slot (masuk · hit · evict · aging · lepas)</h2></div>
      <ul class="timeline" style="max-height:420px;overflow:auto">
        ${w.log.map(l => `<li><span class="tg">${fmt.tgl(l.tanggal)}</span><span>${lfuBadge(l.aksi)} <b>${esc(l.nama)}</b>${l.frekuensi != null ? ` (f=${l.frekuensi})` : ""}<div class="small muted">${esc(l.keterangan || "")}</div></span></li>`).join("")}
      </ul>
    </div>
  </div>`;
};
function lfuBadge(a) {
  const m = { MASUK: "kuning", HIT: "biru", EVICT: "merah", AGING: "abu", LEPAS: "hijau" };
  return `<span class="badge b-${m[a] || "abu"}">${a}</span>`;
}

/* ====================================================== NOTIFIKASI */
ROUTES.notifikasi = async () => {
  const filt = sessionStorage.nf || "";
  const n = await API.get("/api/notifikasi" + (filt ? "?tujuan=" + filt : ""));
  const TC = { ESKALASI: "merah", PRA_ESKALASI: "merah", PEMBEKUAN_PLAFON: "merah", GRACE: "kuning", WATCHLIST: "kuning", PENCAIRAN: "biru", LUNAS: "hijau", PULIH: "hijau" };
  view.innerHTML = `<div class="card">
    <div class="toolbar">
      <select id="nf"><option value="">Semua tujuan</option><option value="PETUGAS">Petugas (AO)</option><option value="COLLECTIONS">Tim Collections</option></select>
      <div style="flex:1"></div><button class="btn" id="baca">Tandai semua dibaca</button>
    </div>
    <table><tr><th>Tanggal</th><th>Tipe</th><th>Tujuan</th><th>Pesan</th></tr>
    ${n.map(x => `<tr style="${x.dibaca ? "" : "font-weight:600;background:#fffdf3"}"><td class="nowrap">${fmt.tgl(x.tanggal)}</td><td><span class="badge b-${TC[x.tipe] || "abu"}">${x.tipe}</span></td><td>${x.tujuan}</td>
      <td>${esc(x.pesan)} ${x.debitur_id ? `<a class="small" href="#debitur/${x.debitur_id}">lihat</a>` : ""}</td></tr>`).join("") || '<tr><td colspan=4 class="empty">Tidak ada notifikasi</td></tr>'}
    </table></div>`;
  $("#nf").value = filt;
  $("#nf").onchange = e => { sessionStorage.nf = e.target.value; ROUTES.notifikasi(); };
  $("#baca").onclick = async () => { await API.post("/api/notifikasi/baca-semua"); ROUTES.notifikasi(); refreshHeader(); };
};

/* ====================================================== PENGAJUAN */
ROUTES.pengajuan = async () => {
  const [kat, deb, pc] = await Promise.all([API.get("/api/kategori"), API.get("/api/debitur"), API.get("/api/pencairan")]);
  const elig = deb.filter(d => ["AKTIF", "MENUNGGU"].includes(d.status));
  const tanpaKredit = deb.filter(d => !["AKTIF", "MENUNGGU", "PENGAWASAN"].includes(d.status) && d.status !== "MACET");
  const antre = pc.filter(p => p.status.startsWith("DITUNDA"));
  view.innerHTML = `
  <div class="grid g2">
    <div class="card">
      <div class="card-head"><h2>① Debitur Baru + Pengajuan KUR</h2></div>
      <form id="f-baru">
        <div class="form-row"><div><label>NIK (16 digit)</label><input name="nik" required pattern="\\d{16}" maxlength="16"></div>
          <div><label>Nama lengkap</label><input name="nama" required></div></div>
        <div class="form-row"><div><label>No. HP</label><input name="no_hp"></div><div><label>Alamat</label><input name="alamat"></div></div>
        <label>Nama usaha</label><input name="nama_usaha" required>
        <label>Kategori usaha (menentukan Max plafon)</label>
        <select name="kategori_id">${kat.map(k => `<option value="${k.id}" data-max="${k.max_plafon}" data-tenor="${k.tenor_maks}">${esc(k.nama)} — maks ${fmt.jt(k.max_plafon)}, bunga ${k.bunga_tahunan}%/th</option>`).join("")}</select>
        <div class="form-row"><div><label>Plafon / Max (Rp)</label><input name="plafon" inputmode="numeric"></div>
          <div><label>Tenor (bulan)</label><input name="tenor_bulan" type="number" value="24" min="1"></div></div>
        <label>Pencairan awal (Rp)</label><input name="pencairan_awal" inputmode="numeric" value="0">
        <p class="hint">Pencairan awal langsung diuji dengan Banker's Algorithm. Plafon kosong = plafon maksimum kategori.</p>
        <button class="btn primary" style="margin-top:8px">Daftarkan &amp; Uji</button>
      </form>
      <div id="out-baru"></div>
    </div>
    <div>
      <div class="card">
        <div class="card-head"><h2>② Pencairan Tambahan (Top-up)</h2></div>
        <form id="f-top">
          <label>Kredit debitur (hanya status Lancar / Menunggu)</label>
          <select name="kredit">${elig.map(d => `<option value="${d.kredit_id}">${esc(d.nama)} — Need ${fmt.jt(d.plafon_max - d.allocation)}</option>`).join("")}</select>
          <label>Jumlah (Rp)</label><input name="jumlah" inputmode="numeric" required>
          <button class="btn primary" style="margin-top:12px">Ajukan Pencairan</button>
        </form>
        <div id="out-top"></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>③ Kredit Baru untuk Debitur Lama</h2></div>
        ${tanpaKredit.length ? `<form id="f-lama">
          <label>Debitur (tanpa kredit aktif)</label>
          <select name="debitur_id">${tanpaKredit.map(d => `<option value="${d.id}">${esc(d.nama)} — skor historis ${d.skor_historis ?? "-"}</option>`).join("")}</select>
          <div class="form-row"><div><label>Tenor (bulan)</label><input name="tenor_bulan" type="number" value="12"></div>
          <div><label>Pencairan awal (Rp)</label><input name="pencairan_awal" inputmode="numeric" value="0"></div></div>
          <button class="btn" style="margin-top:12px">Ajukan</button></form><div id="out-lama"></div>`
          : '<div class="empty">Belum ada debitur yang lunas.</div>'}
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>Antrean Ditunda (${antre.length})</h2><div class="spacer"></div><span class="small muted">Diproses ulang otomatis FIFO saat dana kembali</span></div>
    ${antre.length ? `<table><tr><th>ID</th><th>Debitur</th><th class="num">Jumlah</th><th>Status</th><th>Sejak</th><th></th></tr>
      ${antre.map(p => `<tr><td>#${p.id}</td><td>${esc(p.nama)}</td><td class="num">${fmt.rp(p.jumlah)}</td><td>${badgeP(p.status)}</td><td>${fmt.tgl(p.tanggal_ajuan)}</td>
      <td class="right"><button class="btn sm" data-batal="${p.id}">Batalkan</button></td></tr>`).join("")}</table>` : '<div class="empty">Antrean kosong.</div>'}
  </div>
  <div class="card">
    <div class="card-head"><h2>Riwayat Pencairan</h2></div>
    <div class="table-wrap" style="max-height:420px;overflow:auto"><table><tr><th>ID</th><th>Tgl ajuan</th><th>Debitur</th><th class="num">Jumlah</th><th>Hasil</th><th>Oleh</th></tr>
    ${pc.map(p => `<tr><td>#${p.id}</td><td>${fmt.tgl(p.tanggal_ajuan)}</td><td><a href="#debitur/${p.debitur_id}">${esc(p.nama)}</a></td><td class="num">${fmt.rp(p.jumlah)}</td><td>${badgeP(p.status)}</td><td class="small muted">${esc(p.diajukan_oleh || "")}</td></tr>`).join("")}
    </table></div>
  </div>`;

  $$('input[inputmode="numeric"]').forEach(bindRupiahInput);
  const fb = $("#f-baru");
  const syncKat = () => { const o = fb.kategori_id.selectedOptions[0]; fb.plafon.placeholder = Number(o.dataset.max).toLocaleString("id-ID"); fb.tenor_bulan.max = o.dataset.tenor; };
  fb.kategori_id.onchange = syncKat; syncKat();
  fb.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(fb));
    body.kategori_id = Number(body.kategori_id); body.tenor_bulan = Number(body.tenor_bulan);
    body.plafon = parseRp(body.plafon) || null; body.pencairan_awal = parseRp(body.pencairan_awal);
    try {
      const r = await API.post("/api/debitur", body);
      const pc = r.kredit.pencairan;
      $("#out-baru").innerHTML = `<div class="alert ${r.kredit.status === "DITOLAK" ? "bad" : "ok"}" style="margin-top:12px">
        Debitur #${r.debitur_id} terdaftar. Status kredit: <b>${badge(r.kredit.status)}</b>. ${esc(r.kredit.message)}
        ${pc ? `<div style="margin-top:6px">Pencairan awal: ${badgeP(pc.status)} — ${esc(pc.message)}</div>` : ""}
        ${r.akun ? `<div class="small" style="margin-top:6px">Akun debitur: <b>${esc(r.akun.username)}</b> / ${esc(r.akun.password)}</div>` : ""}
        <div style="margin-top:6px"><a href="#debitur/${r.debitur_id}">Buka detail →</a></div></div>`;
      toast("Debitur berhasil didaftarkan", "ok");
    } catch (ex) { $("#out-baru").innerHTML = `<div class="alert bad" style="margin-top:12px">${esc(ex.message)}</div>`; }
  };
  $("#f-top").onsubmit = async e => {
    e.preventDefault(); const f = e.target;
    try {
      const r = await API.post(`/api/kredit/${f.kredit.value}/pencairan`, { jumlah: parseRp(f.jumlah.value) });
      const names = {}; (await API.get("/api/bankers/state")).proses.forEach(p => names[p.kredit_id] = p.nama.split(" ")[0]);
      toast(r.message, r.granted ? "ok" : "bad");
      await ROUTES.pengajuan();
      $("#out-top").innerHTML = resultHtml(r, names, r.kredit_id);
    } catch (ex) { $("#out-top").innerHTML = `<div class="alert bad" style="margin-top:12px">${esc(ex.message)}</div>`; }
  };
  const fl = $("#f-lama");
  if (fl) fl.onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await API.post("/api/kredit", { debitur_id: Number(fl.debitur_id.value), tenor_bulan: Number(fl.tenor_bulan.value), pencairan_awal: parseRp(fl.pencairan_awal.value) });
      $("#out-lama").innerHTML = `<div class="alert ok" style="margin-top:12px">Kredit #${r.kredit_id}: ${badge(r.status)} ${esc(r.message)}</div>`;
    } catch (ex) { $("#out-lama").innerHTML = `<div class="alert bad" style="margin-top:12px">${esc(ex.message)}</div>`; }
  };
  $$("[data-batal]").forEach(b => b.onclick = async () => {
    try { await API.post(`/api/pencairan/${b.dataset.batal}/batal`); toast("Permintaan dibatalkan"); ROUTES.pengajuan(); }
    catch (ex) { toast(ex.message, "bad"); }
  });
};

/* ====================================================== DEBITUR */
ROUTES.debitur = async (id) => {
  if (id) return detailDebitur(Number(id));
  const f = sessionStorage.f || ""; const q = sessionStorage.q || "";
  const list = await API.get("/api/debitur?" + new URLSearchParams({ ...(f && { status: f }), ...(q && { q }) }));
  view.innerHTML = `<div class="card">
    <div class="toolbar">
      <input id="q" placeholder="Cari nama / usaha / NIK" value="${esc(q)}">
      <select id="f"><option value="">Semua status</option>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("")}</select>
      <div style="flex:1"></div><span class="muted small">${list.length} debitur</span>
      <a class="btn primary" href="#pengajuan">+ Debitur baru</a>
    </div>
    <div class="table-wrap"><table>
      <tr><th>Debitur</th><th>Usaha / Kategori</th><th>Status</th><th class="num">Plafon (Max)</th><th class="num">Outstanding</th><th class="num">Tunggakan</th><th class="num">Insiden</th><th>LFU</th></tr>
      ${list.map(d => `<tr class="${rowCls(d.status)}" style="cursor:pointer" onclick="location.hash='debitur/${d.id}'">
        <td><b>${esc(d.nama)}</b><div class="small muted mono">${esc(d.nik)}</div></td>
        <td>${esc(d.nama_usaha)}<div class="small muted">${esc(d.kategori)}</div></td>
        <td>${badge(d.status)}</td><td class="num">${fmt.jt(d.plafon_max)}</td><td class="num">${fmt.jt(d.allocation)}</td>
        <td class="num">${d.hari_tunggakan ? `<b style="color:${d.hari_tunggakan > 60 ? "var(--merah)" : "var(--kuning)"}">${d.hari_tunggakan} hr</b>` : "0"}</td>
        <td class="num">${d.jumlah_insiden}</td><td>${d.frekuensi_lfu != null ? `<span class="badge b-kuning">slot f=${d.frekuensi_lfu}</span>` : ""}</td></tr>`).join("")}
    </table></div></div>`;
  $("#f").value = f;
  $("#f").onchange = e => { sessionStorage.f = e.target.value; ROUTES.debitur(); };
  let t; $("#q").oninput = e => { clearTimeout(t); t = setTimeout(() => { sessionStorage.q = e.target.value; ROUTES.debitur().then(() => { const i = $("#q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 350); };
};

async function detailDebitur(id, tab = "angsuran") {
  const d = await API.get(`/api/debitur/${id}`);
  const s = STATUS[d.status] || { cls: "abu", label: "-" };
  const aktif = ["AKTIF", "PENGAWASAN"].includes(d.status);
  const belum = d.angsuran.filter(a => a.status === "BELUM");
  const totalSisa = belum.reduce((a, x) => a + x.pokok, 0);
  view.innerHTML = `
  <p><a href="#debitur">← Kembali ke daftar</a></p>
  <div class="status-hero ${s.cls}">
    <div class="lamp">${{ hijau: "✔", kuning: "!", merah: "✖", biru: "★", abu: "…" }[s.cls]}</div>
    <div style="flex:1"><div class="small" style="opacity:.85">${esc(d.nama_usaha)} · ${esc(d.kategori)}</div><h1>${esc(d.nama)}</h1>
      <div>${s.label}${d.hari_tunggakan ? ` · tunggakan ${d.hari_tunggakan} hari` : ""}${d.frekuensi_lfu != null ? ` · di slot pengawasan intensif (frekuensi ${d.frekuensi_lfu})` : ""}</div></div>
    <div class="right"><div class="small" style="opacity:.85">Outstanding</div><div style="font-size:1.4rem;font-weight:800">${fmt.jt(d.allocation)}</div><div class="small">dari plafon ${fmt.jt(d.plafon_max)}</div></div>
  </div>
  <div class="grid g-wide" style="margin-top:16px">
    <div class="card">
      <div class="tabs" id="tabs">
        ${["angsuran", "pencairan", "insiden", "catatan", "riwayat"].map(t => `<button data-t="${t}" class="${t === tab ? "on" : ""}">${{ angsuran: "Jadwal Angsuran", pencairan: "Pencairan", insiden: "Insiden Risiko", catatan: "Catatan Komunikasi", riwayat: "Arsip & Log LFU" }[t]}</button>`).join("")}
      </div>
      <div id="tab-body"></div>
    </div>
    <div>
      <div class="card"><h2>Profil Debitur</h2>
        <dl class="kv"><dt>NIK</dt><dd class="mono">${esc(d.nik)}</dd><dt>No. HP</dt><dd>${esc(d.no_hp || "-")}</dd><dt>Alamat</dt><dd>${esc(d.alamat || "-")}</dd>
          <dt>Terdaftar</dt><dd>${fmt.tgl(d.tanggal_daftar)}</dd><dt>Akun portal</dt><dd>${d.akun ? esc(d.akun.username) : "-"}</dd>
          <dt>Skor historis</dt><dd>${d.skor_historis ?? "belum ada"}</dd><dt>Kredit</dt><dd>#${d.kredit_id ?? "-"} · tenor ${d.tenor_bulan ?? "-"} bln</dd>
          <dt>Sisa pokok</dt><dd>${fmt.rp(totalSisa)} (${belum.length} angsuran)</dd>
          ${d.profil_simulasi ? `<dt>Profil simulasi</dt><dd><span class="badge b-abu">${d.profil_simulasi}</span></dd>` : ""}</dl>
      </div>
      ${aktif ? `<div class="card"><h2>Aksi Petugas</h2>
        <div class="toolbar"><button class="btn primary" id="a-bayar">Catat bayar 1 angsuran</button><button class="btn" id="a-lunas">Pelunasan dipercepat</button></div>
        <div class="toolbar"><button class="btn" id="a-insiden">+ Laporkan insiden</button><button class="btn" id="a-catat">+ Catatan komunikasi</button></div></div>` : ""}
    </div>
  </div>`;
  const body = $("#tab-body");
  const render = t => {
    $$("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === t));
    if (t === "angsuran") body.innerHTML = d.angsuran.length ? `<div class="table-wrap" style="max-height:460px;overflow:auto"><table><tr><th>Ke</th><th>Jatuh tempo</th><th class="num">Pokok</th><th class="num">Bunga</th><th>Status</th><th>Dibayar</th></tr>
      ${d.angsuran.map(a => `<tr><td>${a.angsuran_ke}<span class="small muted"> /P${a.pencairan_id}</span></td><td>${fmt.tgl(a.jatuh_tempo)}</td><td class="num">${fmt.rp(a.pokok)}</td><td class="num">${fmt.rp(a.bunga)}</td>
      <td>${a.status === "DIBAYAR" ? (a.hari_telat > 7 ? '<span class="badge b-kuning">Dibayar telat</span>' : '<span class="badge b-hijau">Dibayar</span>') : a.status === "HAPUS_BUKU" ? '<span class="badge b-merah">Hapus buku</span>' : '<span class="badge b-abu">Belum</span>'}</td>
      <td class="small">${a.tanggal_bayar ? fmt.tgl(a.tanggal_bayar) + (a.hari_telat ? ` (+${a.hari_telat} hr)` : "") : ""}</td></tr>`).join("")}</table></div>` : '<div class="empty">Belum ada jadwal angsuran.</div>';
    if (t === "pencairan") body.innerHTML = `<table><tr><th>ID</th><th>Tanggal</th><th class="num">Jumlah</th><th>Hasil</th><th>Safe sequence</th></tr>
      ${d.pencairan.map(p => `<tr><td>#${p.id}</td><td>${fmt.tgl(p.tanggal_ajuan)}</td><td class="num">${fmt.rp(p.jumlah)}</td><td>${badgeP(p.status)}</td><td class="small mono">${p.safe_sequence ? JSON.parse(p.safe_sequence).map(x => "K" + x).join(" → ") : ""}</td></tr>`).join("")}</table>`;
    if (t === "insiden") body.innerHTML = d.insiden.length ? `<ul class="timeline">${d.insiden.map(i => `<li><span class="tg">${fmt.tgl(i.tanggal)}</span><span><span class="badge b-${i.jenis === "TUNGGAKAN_BERLANJUT" ? "merah" : i.jenis === "USAHA_MENURUN" ? "biru" : "kuning"}">${i.jenis}</span> ${esc(i.keterangan || "")} <span class="small muted">· ${i.sumber}</span></span></li>`).join("")}</ul>` : '<div class="empty">Tidak ada insiden. 👍</div>';
    if (t === "catatan") body.innerHTML = d.catatan.length ? `<ul class="timeline">${d.catatan.map(c => `<li><span class="tg">${fmt.tgl(c.tanggal)}</span><span><b>${esc(c.petugas)}</b>: ${esc(c.isi)}</span></li>`).join("")}</ul>` : '<div class="empty">Belum ada catatan.</div>';
    if (t === "riwayat") body.innerHTML = `<h3>Arsip kredit</h3>${d.arsip.length ? `<table><tr><th>Kredit</th><th>Status akhir</th><th class="num">Dicairkan</th><th class="num">Skor</th><th>Grade</th></tr>${d.arsip.map(a => `<tr><td>#${a.kredit_id}</td><td>${badge(a.status_akhir)}</td><td class="num">${fmt.jt(a.total_dicairkan)}</td><td class="num">${a.skor_kredit}</td><td><b>${a.grade}</b></td></tr>`).join("")}</table>` : '<p class="muted">Belum ada arsip.</p>'}
      <h3 style="margin-top:14px">Log slot LFU</h3><ul class="timeline">${d.watchlist_log.map(l => `<li><span class="tg">${fmt.tgl(l.tanggal)}</span><span>${lfuBadge(l.aksi)} ${l.frekuensi != null ? "f=" + l.frekuensi : ""} <span class="small muted">${esc(l.keterangan || "")}</span></span></li>`).join("") || '<li class="muted">Belum pernah masuk slot.</li>'}</ul>`;
  };
  render(tab);
  $$("#tabs button").forEach(b => b.onclick = () => render(b.dataset.t));
  if (aktif) {
    $("#a-bayar").onclick = async () => {
      try { const r = await API.post(`/api/kredit/${d.kredit_id}/bayar`, { jumlah_angsuran: 1 });
        toast(`Angsuran ke-${r.dibayar[0].ke} tercatat (${fmt.rp(r.dibayar[0].pokok + r.dibayar[0].bunga)})${r.lunas ? " — KREDIT LUNAS!" : ""}`, "ok");
        if (r.antrean_disetujui && r.antrean_disetujui.length) toast(`${r.antrean_disetujui.length} pencairan di antrean ikut disetujui`, "ok");
        detailDebitur(id, "angsuran"); } catch (e) { toast(e.message, "bad"); }
    };
    $("#a-lunas").onclick = () => modal(`<h2>Pelunasan dipercepat</h2><p>Lunasi seluruh sisa pokok <b>${fmt.rp(totalSisa)}</b> + bunga yang sudah jatuh tempo? Bunga mendatang dihapuskan. Plafon (Max) debitur akan dilepas dari simulasi Banker's.</p>
      <div class="modal-foot"><button class="btn" data-close>Batal</button><button class="btn primary" id="ok">Ya, lunasi</button></div>`, bg => {
        $("#ok", bg).onclick = async () => { try { await API.post(`/api/kredit/${d.kredit_id}/lunasi`); closeModal(); toast("Kredit LUNAS & diarsipkan", "ok"); detailDebitur(id, "riwayat"); } catch (e) { toast(e.message, "bad"); } };
      });
    $("#a-insiden").onclick = () => modal(`<h2>Laporkan insiden risiko</h2>
      <label>Jenis</label><select id="j"><option value="USAHA_MENURUN">Laporan usaha menurun</option><option value="LAINNYA">Lainnya</option></select>
      <label>Keterangan</label><textarea id="k" rows="3" placeholder="mis. omzet turun 40% karena renovasi pasar"></textarea>
      <p class="hint">Insiden menambah frekuensi LFU dan mengubah status menjadi Dalam Pengawasan.</p>
      <div class="modal-foot"><button class="btn" data-close>Batal</button><button class="btn primary" id="ok">Simpan</button></div>`, bg => {
        $("#ok", bg).onclick = async () => { try { const r = await API.post(`/api/debitur/${id}/insiden`, { jenis: $("#j", bg).value, keterangan: $("#k", bg).value });
          closeModal(); toast(r.hit ? `Frekuensi naik menjadi ${r.frekuensi}` : `Masuk slot intensif (f=${r.frekuensi})` + (r.evicted ? ` — debitur #${r.evicted.debitur_id} dikeluarkan (LFU)` : ""), "ok"); detailDebitur(id, "insiden"); } catch (e) { toast(e.message, "bad"); } };
      });
    $("#a-catat").onclick = () => modal(`<h2>Catatan komunikasi</h2><textarea id="k" rows="4" placeholder="Hasil telepon / kunjungan"></textarea>
      <div class="modal-foot"><button class="btn" data-close>Batal</button><button class="btn primary" id="ok">Simpan</button></div>`, bg => {
        $("#ok", bg).onclick = async () => { try { await API.post(`/api/debitur/${id}/catatan`, { isi: $("#k", bg).value }); closeModal(); detailDebitur(id, "catatan"); } catch (e) { toast(e.message, "bad"); } };
      });
  }
}

/* ====================================================== ARSIP */
ROUTES.arsip = async () => {
  const a = await API.get("/api/arsip");
  const GC = { A: "hijau", B: "hijau", C: "kuning", D: "kuning", E: "merah" };
  view.innerHTML = `<div class="alert info">Data kredit yang <b>lunas</b> atau <b>macet (hapus buku)</b> tidak dihapus, melainkan diarsipkan sebagai riwayat & skor kredit historis debitur. Skor = 100 − 4×insiden − min(40, maks tunggakan ÷ 3); kredit macet dibatasi maksimal 20.</div>
  <div class="card"><div class="table-wrap"><table>
  <tr><th>Tgl arsip</th><th>Debitur</th><th>Status akhir</th><th class="num">Plafon</th><th class="num">Dicairkan</th><th class="num">Pokok kembali</th><th class="num">Outstanding akhir</th><th class="num">Klaim penjaminan</th><th class="num">Insiden</th><th class="num">Maks DPD</th><th class="num">Skor</th><th>Grade</th></tr>
  ${a.map(x => `<tr class="${rowCls(x.status_akhir)}"><td>${fmt.tgl(x.tanggal_arsip)}</td><td><a href="#debitur/${x.debitur_id}">${esc(x.nama)}</a><div class="small muted">${esc(x.nama_usaha)}</div></td><td>${badge(x.status_akhir)}</td>
    <td class="num">${fmt.jt(x.plafon_max)}</td><td class="num">${fmt.jt(x.total_dicairkan)}</td><td class="num">${fmt.jt(x.total_pokok_dibayar)}</td><td class="num">${fmt.jt(x.outstanding_akhir)}</td><td class="num">${fmt.jt(x.klaim_penjaminan)}</td>
    <td class="num">${x.jumlah_insiden}</td><td class="num">${x.max_hari_tunggakan}</td><td class="num"><b>${x.skor_kredit}</b></td><td><span class="badge b-${GC[x.grade]}">${x.grade}</span></td></tr>`).join("") || '<tr><td colspan=12 class="empty">Belum ada arsip</td></tr>'}
  </table></div></div>`;
};

/* ====================================================== SIMULASI WAKTU */
ROUTES.simulasi = async () => {
  const s = await API.get("/api/sistem"); const p = s.parameter;
  view.innerHTML = `
  <div class="grid g2">
    <div class="card">
      <h2>Jam Sistem (virtual)</h2>
      <div id="bigdate" style="font-size:2rem;font-weight:800;margin:8px 0">${fmt.tgl(p.tanggal_sistem)}</div>
      <p class="muted small">Seluruh aturan Grace Period, Eskalasi, insiden berlanjut, aging LFU, dan antrean pencairan dievaluasi oleh <b>job harian</b> setiap kali hari bertambah.</p>
      <div class="toolbar"><button class="btn primary" data-h="1">+1 hari</button><button class="btn" data-h="7">+7 hari</button><button class="btn" data-h="30">+30 hari</button>
        <input id="hh" type="number" min="1" max="400" placeholder="hari" style="min-width:90px;width:90px"><button class="btn" id="go">Maju</button></div>
    </div>
    <div class="card">
      <h2>Timer Otomatis</h2>
      <p class="small muted">Jika aktif, server memajukan 1 hari virtual setiap <b>${p.auto_timer_detik} detik</b> (demo real-time).</p>
      <div class="toolbar"><span class="badge ${p.auto_timer_aktif ? "b-hijau" : "b-abu"}">${p.auto_timer_aktif ? "AKTIF" : "NONAKTIF"}</span>
        ${ME.peran === "ADMIN" ? `<button class="btn" id="tog">${p.auto_timer_aktif ? "Matikan" : "Nyalakan"} timer</button>` : '<span class="small muted">Hanya admin yang dapat mengubah.</span>'}</div>
      <p class="small muted">Simulasi perilaku debitur dummy: <b>${p.simulasi_perilaku_debitur ? "aktif" : "nonaktif"}</b> (debitur demo membayar sesuai profil DISIPLIN / KADANG_TELAT / BERMASALAH).</p>
    </div>
  </div>
  <div class="card"><h2>Hasil Job Harian</h2><div id="hasil"><div class="empty">Belum ada simulasi pada sesi ini.</div></div></div>`;
  const run = async h => {
    $("#hasil").innerHTML = '<div class="empty">Menjalankan job harian…</div>';
    try {
      const r = await API.post("/api/sistem/maju-hari", { hari: h });
      $("#bigdate").textContent = fmt.tgl(r.tanggal_sistem);
      $("#hasil").innerHTML = `<div class="grid g4">
        <div class="kpi"><div class="label">Tanggal baru</div><div class="value" style="font-size:1.1rem">${fmt.tgl(r.tanggal_sistem)}</div></div>
        <div class="kpi ok"><div class="label">Angsuran dibayar</div><div class="value">${r.dibayar_otomatis}</div></div>
        <div class="kpi warn"><div class="label">Insiden baru / ke pengawasan</div><div class="value">${r.insiden} / ${r.ke_pengawasan}</div></div>
        <div class="kpi bad"><div class="label">Eskalasi NPL</div><div class="value">${r.eskalasi.length}</div></div></div>
        <p class="small">Pulih ke lancar: <b>${r.pulih}</b> · aging LFU: <b>${r.aging}</b> · antrean pencairan disetujui: <b>${r.antrean_disetujui}</b> · pembekuan plafon (pemulihan safe state): <b>${r.pembekuan.length}</b></p>
        <ul class="timeline">${r.notifikasi_baru.map(n => `<li><span class="tg">${fmt.tgl(n.tanggal)}</span><span><span class="badge b-${n.tipe.includes("ESKALASI") || n.tipe === "PEMBEKUAN_PLAFON" ? "merah" : n.tipe === "GRACE" || n.tipe === "WATCHLIST" ? "kuning" : "hijau"}">${n.tipe}</span> <span class="small muted">→ ${n.tujuan}</span> ${esc(n.pesan)}</span></li>`).join("") || '<li class="muted">Tidak ada kejadian.</li>'}</ul>`;
      refreshHeader();
    } catch (e) { $("#hasil").innerHTML = `<div class="alert bad">${esc(e.message)}</div>`; }
  };
  $$("[data-h]").forEach(b => b.onclick = () => run(Number(b.dataset.h)));
  $("#go").onclick = () => run(Number($("#hh").value || 1));
  const tog = $("#tog"); if (tog) tog.onclick = async () => { await API.put("/api/sistem/parameter", { auto_timer_aktif: p.auto_timer_aktif ? 0 : 1 }); ROUTES.simulasi(); refreshHeader(); };
};

/* ====================================================== PENGATURAN */
ROUTES.pengaturan = async () => {
  const [s, kat, log] = await Promise.all([API.get("/api/sistem"), API.get("/api/kategori"), API.get("/api/log")]);
  const p = s.parameter, isAdmin = ME.peran === "ADMIN";
  const F = [["grace_period_hari", "Grace period (hari)", "Toleransi telat sebelum status naik ke Dalam Pengawasan"],
    ["pra_eskalasi_hari", "Peringatan pra-eskalasi (hari)", "Notifikasi dini ke tim collections"],
    ["eskalasi_hari", "Ambang eskalasi NPL (hari)", "Tunggakan > nilai ini → Kredit Macet"],
    ["insiden_berlanjut_tiap_hari", "Insiden berlanjut tiap (hari)", "Insiden tambahan selama tunggakan berlangsung"],
    ["lfu_aging_hari", "Aging LFU (hari)", "Frekuensi turun 1 jika tidak ada insiden selama N hari"],
    ["pemulihan_lancar_hari", "Pemulihan ke Lancar (hari)", "Pengawasan → Lancar setelah N hari bersih"],
    ["persen_penjaminan", "Klaim penjaminan (%)", "Porsi outstanding NPL yang kembali ke Available"],
    ["auto_timer_detik", "Interval timer otomatis (detik)", ""]];
  view.innerHTML = `
  ${isAdmin ? "" : '<div class="alert warn">Mode baca saja — hanya ADMIN yang dapat mengubah pengaturan.</div>'}
  <div class="grid g2">
    <div class="card"><h2>Aturan Grace Period & Eskalasi</h2>
      <form id="fp">${F.map(([k, l, h]) => `<label>${l}</label><input type="number" name="${k}" value="${p[k]}" min="0" ${isAdmin ? "" : "disabled"}>${h ? `<div class="hint">${h}</div>` : ""}`).join("")}
      ${isAdmin ? '<button class="btn primary" style="margin-top:12px">Simpan aturan</button>' : ""}</form>
    </div>
    <div>
      <div class="card"><h2>Kategori Usaha & Max Plafon</h2>
        <table><tr><th>Kode</th><th>Kategori</th><th class="num">Max plafon</th><th class="num">Bunga</th><th class="num">Tenor maks</th></tr>
        ${kat.map(k => `<tr><td class="mono">${k.kode}</td><td>${esc(k.nama)}<div class="small muted">${esc(k.sektor)}</div></td><td class="num">${isAdmin ? `<input data-kat="${k.id}" value="${k.max_plafon.toLocaleString("id-ID")}" style="width:130px;text-align:right">` : fmt.jt(k.max_plafon)}</td><td class="num">${k.bunga_tahunan}%</td><td class="num">${k.tenor_maks} bln</td></tr>`).join("")}</table>
        ${isAdmin ? '<p class="hint">Ubah nilai lalu tekan Enter. Berlaku untuk pengajuan baru.</p>' : ""}
      </div>
      <div class="card"><h2>Kapasitas Slot LFU</h2>
        <div class="toolbar"><input id="cap" type="number" min="1" max="50" value="${p.kapasitas_slot_lfu}" style="min-width:90px;width:90px" ${isAdmin ? "" : "disabled"}>
        ${isAdmin ? '<button class="btn" id="capb">Terapkan</button>' : ""}</div>
        <p class="hint">Mengurangi kapasitas akan meng-evict debitur LFU secara otomatis.</p>
      </div>
      ${isAdmin ? `<div class="card"><h2>Reset Data Demo</h2><p class="small muted">Membangun ulang database dari simulasi Jan–Okt 2026.</p><button class="btn danger" id="reset">Reset ke data demo</button></div>
      <div class="card"><h2>Hapus Semua Data</h2><p class="small muted">Mengosongkan seluruh debitur, kredit, pencairan, angsuran, insiden, notifikasi, dan log. Yang tersisa hanya akun admin/petugas, parameter, kategori usaha, dan dana KUR penuh.</p><button class="btn danger" id="kosongkan">Hapus semua data</button></div>` : ""}
    </div>
  </div>
  <div class="card"><h2>Log Aktivitas (audit trail)</h2>
    <div class="table-wrap" style="max-height:400px;overflow:auto"><table><tr><th>Tgl sistem</th><th>Waktu nyata</th><th>Aktor</th><th>Aksi</th><th>Detail</th></tr>
    ${log.map(l => `<tr><td>${fmt.tgl(l.tanggal)}</td><td class="small muted">${l.waktu_nyata.replace("T", " ")}</td><td>${esc(l.aktor)}</td><td><span class="badge b-abu">${l.aksi}</span></td><td class="small mono">${esc((l.detail || "").slice(0, 120))}</td></tr>`).join("")}</table></div></div>`;
  if (!isAdmin) return;
  $("#fp").onsubmit = async e => {
    e.preventDefault();
    const body = {}; new FormData(e.target).forEach((v, k) => body[k] = Number(v));
    try { await API.put("/api/sistem/parameter", body); toast("Aturan disimpan", "ok"); } catch (ex) { toast(ex.message, "bad"); }
  };
  $$("[data-kat]").forEach(i => { bindRupiahInput(i); i.onkeydown = async e => { if (e.key !== "Enter") return;
    try { await API.put(`/api/kategori/${i.dataset.kat}`, { max_plafon: parseRp(i.value) }); toast("Max plafon diperbarui", "ok"); } catch (ex) { toast(ex.message, "bad"); } }; });
  $("#capb").onclick = async () => { try { const r = await API.put("/api/watchlist/kapasitas", { kapasitas: Number($("#cap").value) }); toast(`Kapasitas diubah. Dikeluarkan: ${r.dikeluarkan.length}`, "ok"); } catch (ex) { toast(ex.message, "bad"); } };
  $("#reset").onclick = () => modal(`<h2>Reset data demo?</h2><p>Semua perubahan akan hilang.</p><div class="modal-foot"><button class="btn" data-close>Batal</button><button class="btn danger" id="ok">Reset</button></div>`,
    bg => { $("#ok", bg).onclick = async () => { await API.post("/api/sistem/reset"); API.logoutLocal(); location.href = "/login.html"; }; });
  $("#kosongkan").onclick = () => modal(`<h2>Hapus semua data?</h2><p>Seluruh debitur dan riwayat kredit akan dihapus permanen. Hanya akun admin/petugas yang tersisa.</p><div class="modal-foot"><button class="btn" data-close>Batal</button><button class="btn danger" id="ok">Hapus</button></div>`,
    bg => { $("#ok", bg).onclick = async () => {
      try { await API.post("/api/sistem/kosongkan"); API.logoutLocal(); location.href = "/login.html"; } catch (ex) { toast(ex.message, "bad"); }
    }; });
};

if (ME) router();
