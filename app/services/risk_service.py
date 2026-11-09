"""
Penanganan Kredit Macet (analogi Deadlock Handling):
  - Grace Period otomatis   : toleransi keterlambatan sebelum status naik ke PENGAWASAN.
  - Eskalasi / Preemption   : tunggakan > ambang -> MACET (NPL), alokasi dicabut dari
                              simulasi Banker's, slot LFU dilepas, notifikasi ke collections.
  - Timer harian            : `daily_job` dijalankan sekali per hari virtual.
"""
from __future__ import annotations

from datetime import date, timedelta

from .. import database as db
from . import kredit_service as ks
from . import watchlist_service as wl


def _d(s: str) -> date:
    return date.fromisoformat(s)


# ------------------------------------------------------- simulasi perilaku
def _hash(*xs) -> int:
    h = 17
    for x in xs:
        h = (h * 31 + int(x) * 2654435761) % 1_000_003
    return h % 100


def rencana_bayar(profil: str, debitur_id: int, a: dict) -> date | None:
    """Tanggal debitur dummy akan membayar angsuran `a` (None = tidak membayar)."""
    jt = _d(a["jatuh_tempo"])
    h = _hash(debitur_id, a["angsuran_ke"], a["pencairan_id"])
    if profil == "DISIPLIN":
        return jt - timedelta(days=h % 3)
    if profil == "KADANG_TELAT":
        return jt + timedelta(days=(h % 4) if h < 65 else 9 + h % 17)
    if profil == "BERMASALAH":
        berhenti_setelah = 1 + debitur_id % 4
        if a["angsuran_ke"] > berhenti_setelah:
            return None
        return jt + timedelta(days=(h % 4) if h < 50 else 9 + h % 20)
    return None


def auto_bayar(c) -> int:
    today = _d(db.today(c))
    n = 0
    for k in db.rows(c, "SELECT k.id, d.id AS debitur_id, d.profil_simulasi FROM kredit k "
                        "JOIN debitur d ON d.id=k.debitur_id WHERE k.status IN ('AKTIF','PENGAWASAN') "
                        "AND d.profil_simulasi IS NOT NULL"):
        while True:
            a = db.row(c, "SELECT * FROM angsuran WHERE kredit_id=? AND status='BELUM' "
                          "ORDER BY jatuh_tempo, id LIMIT 1", (k["id"],))
            if not a:
                break
            plan = rencana_bayar(k["profil_simulasi"], k["debitur_id"], a)
            if plan is None or today < plan:
                break
            ks.bayar_angsuran(c, k["id"], "SIMULASI-DEBITUR", proses=False)
            n += 1
            st = db.row(c, "SELECT status FROM kredit WHERE id=?", (k["id"],))["status"]
            if st not in ("AKTIF", "PENGAWASAN"):
                break
    return n


# ---------------------------------------------------------------- eskalasi
def eskalasi(c, k: dict) -> dict:
    """Preemption: cabut alokasi debitur macet dari simulasi Banker's."""
    persen = db.get_param(c, "persen_penjaminan")
    outstanding = k["allocation"]
    klaim = outstanding * persen // 100
    rugi = outstanding - klaim
    c.execute("UPDATE dana_kur SET available = available + ?, total_klaim_penjaminan = total_klaim_penjaminan + ?, "
              "total_kerugian_npl = total_kerugian_npl + ? WHERE id=1", (klaim, klaim, rugi))
    c.execute("UPDATE angsuran SET status='HAPUS_BUKU' WHERE kredit_id=? AND status='BELUM'", (k["id"],))
    c.execute("UPDATE kredit SET status='MACET', allocation=0, tanggal_selesai=? WHERE id=?",
              (db.today(c), k["id"]))
    c.execute("UPDATE pencairan SET status='DIBATALKAN', keterangan='Kredit macet (eskalasi)' "
              "WHERE kredit_id=? AND status LIKE 'DITUNDA%'", (k["id"],))
    wl.release(c, k["debitur_id"], "Eskalasi: Kredit Macet (NPL) — slot dilepas")
    # simpan outstanding agar arsip benar
    c.execute("UPDATE kredit SET hari_tunggakan=? WHERE id=?", (k["hari_tunggakan"], k["id"]))
    ks.arsipkan(c, k["id"], "MACET", outstanding=outstanding, klaim=klaim)
    nama = k.get("nama") or db.row(c, "SELECT nama FROM debitur WHERE id=?", (k["debitur_id"],))["nama"]
    pesan = (f"ESKALASI: {nama} (kredit #{k['id']}) tunggakan {k['hari_tunggakan']} hari -> KREDIT MACET (NPL). "
             f"Outstanding {ks.rp(outstanding)}; klaim penjaminan {persen}% = {ks.rp(klaim)} kembali ke Available; "
             f"kerugian {ks.rp(rugi)}. Mohon tindak lanjut penagihan.")
    db.notify(c, "ESKALASI", "COLLECTIONS", pesan, k["debitur_id"])
    db.notify(c, "ESKALASI", "PETUGAS", pesan, k["debitur_id"])
    db.notify(c, "ESKALASI", "DEBITUR", "Status kredit Anda ditetapkan MACET. Hubungi petugas KUR segera.",
              k["debitur_id"])
    db.log(c, "SISTEM", "ESKALASI_NPL", {"kredit_id": k["id"], "outstanding": outstanding, "klaim": klaim})
    return {"kredit_id": k["id"], "outstanding": outstanding, "klaim": klaim, "kerugian": rugi}


# ------------------------------------------------- pemulihan safe state
def pulihkan_safe_state(c) -> list[dict]:
    """Deadlock recovery setelah kerugian NPL.

    Kerugian (porsi NPL yang tidak tertutup penjaminan) membuat total dana yang dapat
    kembali berkurang, sehingga state yang tadinya SAFE bisa menjadi UNSAFE. Sistem lalu
    MEMBEKUKAN sisa plafon (Max := Allocation, Need := 0) satu per satu — prioritas
    debitur Dalam Pengawasan, lalu Need terbesar — sampai state kembali SAFE.
    Debitur yang dibekukan tetap membayar angsuran normal; hanya hak tarik tambahannya hilang.
    """
    from ..algorithms import bankers
    dibekukan = []
    while True:
        available, max_, alloc, kred = ks.banker_state(c)
        if bankers.is_safe(available, max_, alloc).safe:
            return dibekukan
        kandidat = sorted([k for k in kred if k["plafon_max"] > k["allocation"]],
                          key=lambda k: (k["status"] != "PENGAWASAN", -(k["plafon_max"] - k["allocation"])))
        if not kandidat:  # tidak mungkin terjadi: semua Need = 0 selalu SAFE
            return dibekukan
        k = kandidat[0]
        need = k["plafon_max"] - k["allocation"]
        if k["allocation"] == 0:
            c.execute("UPDATE kredit SET plafon_max=0, status='DITOLAK', tanggal_selesai=? WHERE id=?",
                      (db.today(c), k["id"]))
        else:
            c.execute("UPDATE kredit SET plafon_max=allocation WHERE id=?", (k["id"],))
        c.execute("UPDATE pencairan SET status='DIBATALKAN', tanggal_proses=?, keterangan=? "
                  "WHERE kredit_id=? AND status LIKE 'DITUNDA%'",
                  (db.today(c), "Plafon dibekukan (pemulihan safe state)", k["id"]))
        db.notify(c, "PEMBEKUAN_PLAFON", "PETUGAS",
                  f"Pemulihan safe state: sisa plafon {k['nama']} ({ks.rp(need)}) DIBEKUKAN karena kerugian NPL "
                  f"mengurangi kapasitas dana.", k["debitur_id"])
        db.notify(c, "PEMBEKUAN_PLAFON", "DEBITUR",
                  f"Sisa plafon Anda ({ks.rp(need)}) dibekukan sementara oleh sistem. Angsuran berjalan seperti biasa.",
                  k["debitur_id"])
        db.log(c, "SISTEM", "PEMBEKUAN_PLAFON", {"kredit_id": k["id"], "need_dibekukan": need})
        dibekukan.append({"kredit_id": k["id"], "need": need})


# ---------------------------------------------------------------- job harian
def daily_job(c) -> dict:
    today = db.today(c)
    p = db.all_params(c)
    grace, pra, esk, step, pulih = (p["grace_period_hari"], p["pra_eskalasi_hari"], p["eskalasi_hari"],
                                    p["insiden_berlanjut_tiap_hari"], p["pemulihan_lancar_hari"])
    ringkas = {"tanggal": today, "dibayar_otomatis": 0, "insiden": 0, "ke_pengawasan": 0,
               "pulih": 0, "eskalasi": [], "pembekuan": [], "aging": 0, "antrean_disetujui": 0}
    if p["simulasi_perilaku_debitur"]:
        ringkas["dibayar_otomatis"] = auto_bayar(c)

    batas_grace = (_d(today) - timedelta(days=grace)).isoformat()
    for k in db.rows(c, "SELECT k.*, d.nama FROM kredit k JOIN debitur d ON d.id=k.debitur_id "
                        "WHERE k.status IN ('AKTIF','PENGAWASAN') ORDER BY k.id"):
        dpd = ks.hari_tunggakan(c, k["id"], today)
        c.execute("UPDATE kredit SET hari_tunggakan=?, max_hari_tunggakan=MAX(max_hari_tunggakan, ?) WHERE id=?",
                  (dpd, dpd, k["id"]))
        k["hari_tunggakan"] = dpd

        # 1) Grace period terlewati -> insiden + status PENGAWASAN
        for a in db.rows(c, "SELECT * FROM angsuran WHERE kredit_id=? AND status='BELUM' AND insiden_dicatat=0 "
                            "AND jatuh_tempo < ?", (k["id"], batas_grace)):
            c.execute("UPDATE angsuran SET insiden_dicatat=1 WHERE id=?", (a["id"],))
            wl.record_incident(c, k["debitur_id"], "TELAT_BAYAR",
                               f"Angsuran ke-{a['angsuran_ke']} lewat grace period {grace} hari", k["id"])
            ringkas["insiden"] += 1
            if k["status"] == "AKTIF":
                c.execute("UPDATE kredit SET status='PENGAWASAN' WHERE id=?", (k["id"],))
                k["status"] = "PENGAWASAN"
                ringkas["ke_pengawasan"] += 1
                db.notify(c, "GRACE", "PETUGAS",
                          f"{k['nama']} melewati grace period {grace} hari -> status DALAM PENGAWASAN.",
                          k["debitur_id"])
                db.notify(c, "GRACE", "DEBITUR",
                          f"Angsuran Anda terlambat lebih dari {grace} hari. Status: DALAM PENGAWASAN.",
                          k["debitur_id"])

        # 2) Tunggakan berlanjut -> insiden tambahan tiap `step` hari
        if dpd > grace and step > 0 and dpd % step == 0:
            wl.record_incident(c, k["debitur_id"], "TUNGGAKAN_BERLANJUT", f"Tunggakan mencapai {dpd} hari", k["id"])
            ringkas["insiden"] += 1

        # 3) Peringatan pra-eskalasi
        if dpd == pra:
            db.notify(c, "PRA_ESKALASI", "COLLECTIONS",
                      f"PERINGATAN: {k['nama']} menunggak {dpd} hari. Eskalasi NPL pada hari ke-{esk + 1}.",
                      k["debitur_id"])

        # 4) Eskalasi otomatis (preemption)
        if dpd > esk:
            ringkas["eskalasi"].append(eskalasi(c, k))
            continue

        # 5) Pemulihan: PENGAWASAN -> AKTIF (Lancar)
        if k["status"] == "PENGAWASAN" and dpd == 0:
            last = c.execute("SELECT MAX(tanggal) FROM insiden_risiko WHERE kredit_id=?", (k["id"],)).fetchone()[0]
            if last is None or (_d(today) - _d(last)).days >= pulih:
                c.execute("UPDATE kredit SET status='AKTIF' WHERE id=?", (k["id"],))
                ringkas["pulih"] += 1
                db.notify(c, "PULIH", "PETUGAS", f"{k['nama']} kembali LANCAR ({pulih} hari tanpa insiden).",
                          k["debitur_id"])

    if ringkas["eskalasi"]:
        ringkas["pembekuan"] = pulihkan_safe_state(c)
    ringkas["aging"] = len(wl.aging(c))
    ringkas["antrean_disetujui"] = len(ks.proses_antrean(c))
    return ringkas


def maju_hari(c, n: int = 1) -> dict:
    if n < 1 or n > 400:
        raise ks.BisnisError("Jumlah hari 1 s.d. 400")
    notif0 = c.execute("SELECT COALESCE(MAX(id),0) FROM notifikasi").fetchone()[0]
    total = {"dibayar_otomatis": 0, "insiden": 0, "ke_pengawasan": 0, "pulih": 0, "eskalasi": [],
             "pembekuan": [], "aging": 0, "antrean_disetujui": 0}
    for _ in range(n):
        nxt = (_d(db.today(c)) + timedelta(days=1)).isoformat()
        db.set_param(c, "tanggal_sistem", nxt)
        r = daily_job(c)
        for key in total:
            total[key] += r[key]
    total["tanggal_sistem"] = db.today(c)
    total["notifikasi_baru"] = db.rows(c, "SELECT * FROM notifikasi WHERE id>? AND tujuan!='DEBITUR' ORDER BY id",
                                       (notif0,))
    db.log(c, "TIMER", "MAJU_HARI", {"hari": n, "sampai": total["tanggal_sistem"]})
    return total
