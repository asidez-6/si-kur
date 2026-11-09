/* SI-KUR — Portal Debitur: bahasa sederhana untuk pelaku UMKM */
const ME = requireRole(["DEBITUR"]);
const PESAN = {
  AKTIF: ["hijau", "😊", "Kredit Anda LANCAR", "Terima kasih telah membayar tepat waktu. Pertahankan!"],
  PENGAWASAN: ["kuning", "⚠️", "Kredit Anda DALAM PENGAWASAN", "Ada angsuran yang terlambat atau laporan risiko. Segera lunasi tunggakan agar status kembali hijau."],
  MACET: ["merah", "⛔", "Kredit Anda MACET", "Tunggakan melewati batas. Silakan hubungi petugas KUR untuk penyelesaian."],
  LUNAS: ["abu", "🎉", "Kredit Anda sudah LUNAS", "Riwayat baik Anda tersimpan sebagai skor kredit untuk pengajuan berikutnya."],
  MENUNGGU: ["abu", "⏳", "Menunggu Pencairan", "Pengajuan Anda sedang menunggu ketersediaan dana yang aman."],
};

async function load() {
  const d = await API.get("/api/saya");
  $("#tgl").textContent = "Hari ini: " + fmt.tgl(d.tanggal_sistem);
  const [cls, ico, judul, sub] = PESAN[d.status] || ["abu", "•", "Belum ada kredit", ""];
  const ang = d.angsuran;
  const belum = ang.filter(a => a.status === "BELUM");
  const next = belum[0];
  const telat = belum.filter(a => a.jatuh_tempo < d.tanggal_sistem);
  const dibayar = ang.filter(a => a.status === "DIBAYAR").length;
  const totalTagihanTelat = telat.reduce((s, a) => s + a.pokok + a.bunga, 0);
  const sisaPlafon = (d.plafon_max || 0) - (d.allocation || 0);
  const pending = d.pencairan.find(p => p.status.startsWith("DITUNDA"));
  const unread = d.notifikasi.filter(n => !n.dibaca).length;

  $("#view").innerHTML = `
  <h1 style="margin-top:6px">Halo, ${esc(d.nama.split(" ")[0])} 👋</h1>
  <p class="muted">${esc(d.nama_usaha)} · ${esc(d.kategori)}</p>
  <div class="status-hero ${cls}"><div class="lamp">${ico}</div><div><h1>${judul}</h1><div>${sub}</div></div></div>
  ${telat.length ? `<div class="alert bad" style="margin-top:14px"><b>Anda punya ${telat.length} angsuran terlambat</b> (total ${fmt.rp(totalTagihanTelat)}), tunggakan ${d.hari_tunggakan} hari.
     Batas toleransi (grace period) adalah 7 hari; tunggakan lebih dari 90 hari akan membuat kredit berstatus MACET.</div>` : ""}
  <div class="grid g3" style="margin-top:16px">
    <div class="kpi accent"><div class="label">Sisa pinjaman</div><div class="value">${fmt.rp(d.allocation)}</div><div class="sub">dari plafon ${fmt.rp(d.plafon_max)}</div></div>
    <div class="kpi ${next && next.jatuh_tempo < d.tanggal_sistem ? "bad" : "ok"}"><div class="label">Angsuran berikutnya</div>
      <div class="value">${next ? fmt.rp(next.pokok + next.bunga) : "-"}</div><div class="sub">${next ? "jatuh tempo " + fmt.tgl(next.jatuh_tempo) : "tidak ada"}</div></div>
    <div class="kpi"><div class="label">Progres angsuran</div><div class="value">${dibayar} / ${ang.length}</div>
      <div class="progress" style="margin-top:6px"><span style="width:${fmt.pct(dibayar, ang.length || 1)}%"></span></div></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card">
      <h2>Ajukan Pencairan Tambahan</h2>
      ${d.status === "AKTIF" || d.status === "MENUNGGU" ? `
        <p class="small muted">Sisa plafon yang bisa dicairkan: <b>${fmt.rp(sisaPlafon)}</b>. Sistem akan mengecek apakah dana KUR tetap aman untuk semua debitur sebelum mencairkan.</p>
        ${pending ? `<div class="alert warn">Permintaan ${fmt.rp(pending.jumlah)} sedang <b>menunggu</b> (${badgeP(pending.status)}). Akan diproses otomatis saat dana tersedia.</div>` : `
        <form id="fp"><label>Jumlah (Rp)</label><input id="jml" inputmode="numeric" required placeholder="mis. 5.000.000">
        <button class="btn primary" style="margin-top:10px">Ajukan</button></form><div id="out"></div>`}`
        : `<p class="muted">Pencairan tambahan hanya untuk kredit berstatus Lancar.</p>`}
    </div>
    <div class="card">
      <div class="card-head"><h2>Pemberitahuan</h2><div class="spacer"></div>${unread ? `<button class="btn sm" id="rd">Tandai dibaca (${unread})</button>` : ""}</div>
      <ul class="timeline" style="max-height:260px;overflow:auto">${d.notifikasi.map(n => `<li style="${n.dibaca ? "" : "font-weight:600"}"><span class="tg">${fmt.tgl(n.tanggal)}</span><span>${esc(n.pesan)}</span></li>`).join("") || '<li class="muted">Belum ada pemberitahuan.</li>'}</ul>
    </div>
  </div>
  <div class="card">
    <h2>Jadwal Angsuran</h2>
    <div class="table-wrap" style="max-height:420px;overflow:auto"><table><tr><th>Ke</th><th>Jatuh tempo</th><th class="num">Pokok</th><th class="num">Bunga</th><th class="num">Total</th><th>Status</th></tr>
    ${ang.map(a => { const lewat = a.status === "BELUM" && a.jatuh_tempo < d.tanggal_sistem;
      return `<tr class="${a.status === "DIBAYAR" ? "row-hijau" : lewat ? "row-merah" : a.status === "HAPUS_BUKU" ? "row-merah" : ""}"><td>${a.angsuran_ke}</td><td>${fmt.tgl(a.jatuh_tempo)}</td><td class="num">${fmt.rp(a.pokok)}</td><td class="num">${fmt.rp(a.bunga)}</td><td class="num"><b>${fmt.rp(a.pokok + a.bunga)}</b></td>
      <td>${a.status === "DIBAYAR" ? `<span class="badge b-hijau">Sudah dibayar ${fmt.tgl(a.tanggal_bayar)}</span>` : lewat ? '<span class="badge b-merah">Terlambat</span>' : a.status === "HAPUS_BUKU" ? '<span class="badge b-merah">Hapus buku</span>' : '<span class="badge b-abu">Belum jatuh tempo</span>'}</td></tr>`; }).join("") || '<tr><td colspan=6 class="empty">Belum ada jadwal</td></tr>'}
    </table></div>
    <p class="hint">Pembayaran dilakukan melalui petugas/teller bank penyalur; status di sini diperbarui setelah petugas mencatat pembayaran.</p>
  </div>
  <div class="grid g2">
    <div class="card"><h2>Riwayat Kredit</h2>
      ${d.arsip.length ? `<table><tr><th>Kredit</th><th>Status</th><th class="num">Skor</th><th>Grade</th></tr>${d.arsip.map(a => `<tr><td>#${a.kredit_id} · ${fmt.tgl(a.tanggal_arsip)}</td><td>${badge(a.status_akhir)}</td><td class="num">${a.skor_kredit}</td><td><b>${a.grade}</b></td></tr>`).join("")}</table>` : '<p class="muted">Belum ada kredit yang selesai.</p>'}
    </div>
    <div class="card"><h2>Arti Warna Status</h2>
      <ol class="help-steps">
        <li><span class="badge b-hijau">Hijau · Lancar</span> — semua angsuran dibayar paling lambat 7 hari setelah jatuh tempo.</li>
        <li><span class="badge b-kuning">Kuning · Dalam Pengawasan</span> — terlambat lebih dari 7 hari atau ada laporan usaha menurun. Kembali hijau setelah 30 hari tanpa masalah.</li>
        <li><span class="badge b-merah">Merah · Macet</span> — tunggakan lebih dari 90 hari. Kredit dihentikan dan diteruskan ke tim penagihan.</li>
      </ol>
    </div>
  </div>`;
  const fp = $("#fp");
  if (fp) { bindRupiahInput($("#jml")); fp.onsubmit = async e => { e.preventDefault();
    try { const r = await API.post("/api/saya/pencairan", { jumlah: parseRp($("#jml").value) });
      $("#out").innerHTML = `<div class="alert ${r.granted ? "ok" : "warn"}" style="margin-top:10px">${badgeP(r.status)} ${esc(r.granted ? "Pencairan disetujui! Jadwal angsuran baru telah dibuat." : r.message)}</div>`;
      setTimeout(load, 1800);
    } catch (ex) { $("#out").innerHTML = `<div class="alert bad" style="margin-top:10px">${esc(ex.message)}</div>`; } }; }
  const rd = $("#rd"); if (rd) rd.onclick = async () => { await API.post("/api/saya/notifikasi/baca"); load(); };
}
if (ME) load().catch(e => $("#view").innerHTML = `<div class="alert bad">${esc(e.message)}</div>`);
