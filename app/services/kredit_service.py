"""Logika bisnis siklus kredit: pengajuan, pencairan (Banker's), angsuran, pelunasan, arsip."""
from __future__ import annotations

import json
from datetime import date, timedelta

from .. import database as db
from ..algorithms import bankers
from . import watchlist_service as wl

ACTIVE = ("MENUNGGU", "AKTIF", "PENGAWASAN")


class BisnisError(Exception):
    pass


def rp(x: int) -> str:
    return "Rp " + f"{int(x):,}".replace(",", ".")


# ===================================================================== state
def banker_state(c):
    dana = db.row(c, "SELECT * FROM dana_kur WHERE id=1")
    ks = db.rows(c, f"SELECT k.*, d.nama FROM kredit k JOIN debitur d ON d.id=k.debitur_id "
                    f"WHERE k.status IN {ACTIVE} ORDER BY k.id")
    max_ = {k["id"]: [k["plafon_max"]] for k in ks}
    alloc = {k["id"]: [k["allocation"]] for k in ks}
    return [dana["available"]], max_, alloc, ks


def banker_snapshot(c) -> dict:
    available, max_, alloc, ks = banker_state(c)
    safety = bankers.is_safe(available, max_, alloc)
    dana = db.row(c, "SELECT * FROM dana_kur WHERE id=1")
    total_alloc = sum(a[0] for a in alloc.values())
    return {
        "available": available[0],
        "pagu": dana["pagu"],
        "total_allocation": total_alloc,
        "total_need": sum(max_[p][0] - alloc[p][0] for p in max_),
        "total_kerugian_npl": dana["total_kerugian_npl"],
        "total_klaim_penjaminan": dana["total_klaim_penjaminan"],
        "proses": [{"kredit_id": k["id"], "debitur_id": k["debitur_id"], "nama": k["nama"],
                    "status": k["status"], "max": k["plafon_max"], "allocation": k["allocation"],
                    "need": k["plafon_max"] - k["allocation"]} for k in ks],
        "safety": safety.to_dict(),
    }


def check_invariant(c) -> bool:
    """Available + ΣAllocation(aktif) + Kerugian NPL == Pagu (konservasi dana)."""
    dana = db.row(c, "SELECT * FROM dana_kur WHERE id=1")
    s = c.execute(f"SELECT COALESCE(SUM(allocation),0) FROM kredit WHERE status IN {ACTIVE}").fetchone()[0]
    return dana["available"] + s + dana["total_kerugian_npl"] == dana["pagu"]


# ================================================================ pengajuan
def ajukan_kredit(c, debitur_id: int, plafon: int, tenor: int, pencairan_awal: int, aktor: str) -> dict:
    deb = db.row(c, "SELECT d.*, k.max_plafon, k.bunga_tahunan, k.tenor_maks, k.nama AS kategori "
                    "FROM debitur d JOIN kategori_usaha k ON k.id=d.kategori_id WHERE d.id=?", (debitur_id,))
    if not deb:
        raise BisnisError("Debitur tidak ditemukan")
    if plafon <= 0 or plafon > deb["max_plafon"]:
        raise BisnisError(f"Plafon harus 1 s.d. {rp(deb['max_plafon'])} untuk kategori {deb['kategori']}")
    if tenor < 1 or tenor > deb["tenor_maks"]:
        raise BisnisError(f"Tenor harus 1 s.d. {deb['tenor_maks']} bulan")
    if pencairan_awal < 0 or pencairan_awal > plafon:
        raise BisnisError("Pencairan awal tidak boleh melebihi plafon")
    aktif = db.row(c, f"SELECT id FROM kredit WHERE debitur_id=? AND status IN {ACTIVE}", (debitur_id,))
    if aktif:
        raise BisnisError("Debitur masih memiliki kredit aktif (satu debitur satu fasilitas KUR)")
    hist = db.row(c, "SELECT status_akhir FROM arsip_kredit WHERE debitur_id=? AND status_akhir='MACET'",
                  (debitur_id,))
    if hist:
        raise BisnisError("Debitur memiliki riwayat Kredit Macet (NPL) — tidak dapat mengajukan KUR baru")

    today = db.today(c)
    available, max_, alloc, _ = banker_state(c)
    kapasitas = available[0] + sum(a[0] for a in alloc.values())
    if plafon > kapasitas:
        cid = c.execute("INSERT INTO kredit(debitur_id,plafon_max,tenor_bulan,bunga_tahunan,status,tanggal_pengajuan,"
                        "tanggal_selesai) VALUES(?,?,?,?, 'DITOLAK', ?, ?)",
                        (debitur_id, plafon, tenor, deb["bunga_tahunan"], today, today)).lastrowid
        db.log(c, aktor, "KREDIT_DITOLAK", {"kredit_id": cid, "alasan": "Max > kapasitas dana"})
        return {"kredit_id": cid, "status": "DITOLAK",
                "message": f"Plafon {rp(plafon)} melebihi kapasitas dana yang dapat kembali ({rp(kapasitas)})."}

    cid = c.execute("INSERT INTO kredit(debitur_id,plafon_max,tenor_bulan,bunga_tahunan,status,tanggal_pengajuan,"
                    "terakhir_bersih) VALUES(?,?,?,?, 'MENUNGGU', ?, ?)",
                    (debitur_id, plafon, tenor, deb["bunga_tahunan"], today, today)).lastrowid
    db.log(c, aktor, "KREDIT_DIAJUKAN", {"kredit_id": cid, "plafon": plafon, "tenor": tenor})
    out = {"kredit_id": cid, "status": "MENUNGGU", "message": "Kredit terdaftar sebagai proses baru."}
    if pencairan_awal > 0:
        out["pencairan"] = ajukan_pencairan(c, cid, pencairan_awal, aktor)
        out["status"] = db.row(c, "SELECT status FROM kredit WHERE id=?", (cid,))["status"]
    return out


def _eligible(k) -> str | None:
    if k is None:
        return "Kredit tidak ditemukan"
    if k["status"] not in ("MENUNGGU", "AKTIF"):
        return f"Kredit berstatus {k['status']} — pencairan tambahan tidak diizinkan"
    return None


def simulasi_pencairan(c, kredit_id: int, jumlah: int) -> dict:
    """What-if: jalankan Resource-Request Algorithm tanpa menyimpan apa pun."""
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (kredit_id,))
    err = _eligible(k)
    if err:
        raise BisnisError(err)
    if jumlah <= 0:
        raise BisnisError("Jumlah pencairan harus > 0")
    available, max_, alloc, _ = banker_state(c)
    return bankers.request_resources(kredit_id, [jumlah], available, max_, alloc).to_dict()


def ajukan_pencairan(c, kredit_id: int, jumlah: int, aktor: str) -> dict:
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (kredit_id,))
    err = _eligible(k)
    if err:
        raise BisnisError(err)
    if jumlah <= 0:
        raise BisnisError("Jumlah pencairan harus > 0")
    pending = db.row(c, "SELECT id FROM pencairan WHERE kredit_id=? AND status LIKE 'DITUNDA%'", (kredit_id,))
    if pending:
        raise BisnisError("Masih ada permintaan pencairan yang menunggu untuk kredit ini")
    today = db.today(c)
    pid = c.execute("INSERT INTO pencairan(kredit_id,jumlah,status,tanggal_ajuan,diajukan_oleh) "
                    "VALUES(?,?, 'BARU', ?, ?)", (kredit_id, jumlah, today, aktor)).lastrowid
    return _proses_pencairan(c, pid, aktor)


def _proses_pencairan(c, pencairan_id: int, aktor: str) -> dict:
    p = db.row(c, "SELECT * FROM pencairan WHERE id=?", (pencairan_id,))
    k = db.row(c, "SELECT k.*, d.nama FROM kredit k JOIN debitur d ON d.id=k.debitur_id WHERE k.id=?",
               (p["kredit_id"],))
    today = db.today(c)
    available, max_, alloc, _ = banker_state(c)
    res = bankers.request_resources(k["id"], [p["jumlah"]], available, max_, alloc)
    seq = json.dumps(res.safety.sequence) if res.safety else None

    if res.granted:
        c.execute("UPDATE dana_kur SET available = available - ? WHERE id=1", (p["jumlah"],))
        c.execute("UPDATE kredit SET allocation = allocation + ?, total_dicairkan = total_dicairkan + ?, "
                  "status = CASE WHEN status='MENUNGGU' THEN 'AKTIF' ELSE status END, "
                  "tanggal_cair_pertama = COALESCE(tanggal_cair_pertama, ?) WHERE id=?",
                  (p["jumlah"], p["jumlah"], today, k["id"]))
        c.execute("UPDATE pencairan SET status=?, tanggal_proses=?, safe_sequence=?, keterangan=? WHERE id=?",
                  (res.status, today, seq, res.message, pencairan_id))
        _buat_jadwal(c, k, pencairan_id, p["jumlah"], today)
        db.notify(c, "PENCAIRAN", "DEBITUR", f"Pencairan {rp(p['jumlah'])} DISETUJUI.", k["debitur_id"])
        db.log(c, aktor, "PENCAIRAN_DISETUJUI", {"pencairan_id": pencairan_id, "kredit_id": k["id"],
                                                  "jumlah": p["jumlah"], "safe_sequence": res.safety.sequence})
    elif res.status.startswith("DITUNDA"):
        if p["status"] == "BARU":
            db.notify(c, "PENCAIRAN", "DEBITUR",
                      f"Pencairan {rp(p['jumlah'])} DITUNDA: {res.message}", k["debitur_id"])
            db.log(c, aktor, res.status, {"pencairan_id": pencairan_id, "kredit_id": k["id"], "jumlah": p["jumlah"]})
        c.execute("UPDATE pencairan SET status=?, keterangan=?, safe_sequence=? WHERE id=?",
                  (res.status, res.message, seq, pencairan_id))
    else:
        c.execute("UPDATE pencairan SET status=?, tanggal_proses=?, keterangan=? WHERE id=?",
                  (res.status, today, res.message, pencairan_id))
        db.log(c, aktor, res.status, {"pencairan_id": pencairan_id, "kredit_id": k["id"]})

    out = res.to_dict()
    out["pencairan_id"] = pencairan_id
    out["kredit_id"] = k["id"]
    return out


def proses_antrean(c, aktor="SISTEM") -> list[dict]:
    """Coba ulang permintaan yang DITUNDA (FIFO) setiap ada dana kembali."""
    hasil = []
    for p in db.rows(c, "SELECT p.id, k.status FROM pencairan p JOIN kredit k ON k.id=p.kredit_id "
                        "WHERE p.status LIKE 'DITUNDA%' ORDER BY p.id"):
        if p["status"] not in ("MENUNGGU", "AKTIF"):
            c.execute("UPDATE pencairan SET status='DIBATALKAN', tanggal_proses=?, keterangan=? WHERE id=?",
                      (db.today(c), f"Dibatalkan otomatis: kredit berstatus {p['status']}", p["id"]))
            continue
        r = _proses_pencairan(c, p["id"], aktor)
        if r["granted"]:
            hasil.append(r)
    return hasil


def batalkan_pencairan(c, pencairan_id: int, aktor: str):
    p = db.row(c, "SELECT * FROM pencairan WHERE id=?", (pencairan_id,))
    if not p or not p["status"].startswith("DITUNDA"):
        raise BisnisError("Hanya permintaan berstatus DITUNDA yang bisa dibatalkan")
    c.execute("UPDATE pencairan SET status='DIBATALKAN', tanggal_proses=?, keterangan=? WHERE id=?",
              (db.today(c), f"Dibatalkan oleh {aktor}", pencairan_id))
    # kredit yang belum pernah cair -> proses keluar dari sistem (klaim Max dilepas)
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (p["kredit_id"],))
    if k["status"] == "MENUNGGU" and k["allocation"] == 0:
        c.execute("UPDATE kredit SET status='DITOLAK', tanggal_selesai=? WHERE id=?", (db.today(c), k["id"]))
    db.log(c, aktor, "PENCAIRAN_DIBATALKAN", {"pencairan_id": pencairan_id})


def _buat_jadwal(c, k: dict, pencairan_id: int, jumlah: int, tgl: str) -> None:
    n = k["tenor_bulan"]
    pokok = jumlah // n
    sisa = jumlah - pokok * n
    bunga = round(jumlah * k["bunga_tahunan"] / 100 / 12)
    start = date.fromisoformat(tgl)
    for i in range(1, n + 1):
        jt = start + timedelta(days=30 * i)
        c.execute("INSERT INTO angsuran(kredit_id,pencairan_id,angsuran_ke,jatuh_tempo,pokok,bunga) "
                  "VALUES(?,?,?,?,?,?)", (k["id"], pencairan_id, i, jt.isoformat(),
                                          pokok + (sisa if i == n else 0), bunga))


# ================================================================ pembayaran
def hari_tunggakan(c, kredit_id: int, today: str | None = None) -> int:
    today = today or db.today(c)
    r = c.execute("SELECT MIN(jatuh_tempo) FROM angsuran WHERE kredit_id=? AND status='BELUM' AND jatuh_tempo < ?",
                  (kredit_id, today)).fetchone()[0]
    return (date.fromisoformat(today) - date.fromisoformat(r)).days if r else 0


def bayar_angsuran(c, kredit_id: int, aktor: str, jumlah_angsuran: int = 1, proses=True) -> dict:
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (kredit_id,))
    if not k or k["status"] not in ("AKTIF", "PENGAWASAN"):
        raise BisnisError("Kredit tidak aktif")
    today = db.today(c)
    dibayar = []
    for _ in range(jumlah_angsuran):
        a = db.row(c, "SELECT * FROM angsuran WHERE kredit_id=? AND status='BELUM' ORDER BY jatuh_tempo, id LIMIT 1",
                   (kredit_id,))
        if not a:
            break
        telat = max(0, (date.fromisoformat(today) - date.fromisoformat(a["jatuh_tempo"])).days)
        c.execute("UPDATE angsuran SET status='DIBAYAR', tanggal_bayar=?, hari_telat=? WHERE id=?",
                  (today, telat, a["id"]))
        _terima_dana(c, kredit_id, a["pokok"], a["bunga"])
        dibayar.append({"angsuran_id": a["id"], "ke": a["angsuran_ke"], "pokok": a["pokok"],
                        "bunga": a["bunga"], "hari_telat": telat})
    if not dibayar:
        raise BisnisError("Tidak ada angsuran yang belum dibayar")
    db.log(c, aktor, "BAYAR_ANGSURAN", {"kredit_id": kredit_id, "angsuran": [d["angsuran_id"] for d in dibayar]})
    hasil = {"dibayar": dibayar, "lunas": False}
    dpd = hari_tunggakan(c, kredit_id)
    c.execute("UPDATE kredit SET hari_tunggakan=? WHERE id=?", (dpd, kredit_id))
    if _cek_lunas(c, kredit_id):
        hasil["lunas"] = True
    if proses:
        hasil["antrean_disetujui"] = proses_antrean(c)
    return hasil


def lunasi(c, kredit_id: int, aktor: str) -> dict:
    """Pelunasan dipercepat: seluruh pokok sisa + bunga yang sudah jatuh tempo; bunga mendatang dihapus."""
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (kredit_id,))
    if not k or k["status"] not in ("AKTIF", "PENGAWASAN"):
        raise BisnisError("Kredit tidak aktif")
    today = db.today(c)
    rows_ = db.rows(c, "SELECT * FROM angsuran WHERE kredit_id=? AND status='BELUM'", (kredit_id,))
    tot_pokok = tot_bunga = 0
    for a in rows_:
        bunga = a["bunga"] if a["jatuh_tempo"] <= today else 0
        telat = max(0, (date.fromisoformat(today) - date.fromisoformat(a["jatuh_tempo"])).days)
        c.execute("UPDATE angsuran SET status='DIBAYAR', tanggal_bayar=?, hari_telat=?, bunga=? WHERE id=?",
                  (today, telat, bunga, a["id"]))
        tot_pokok += a["pokok"]
        tot_bunga += bunga
    if tot_pokok:
        _terima_dana(c, kredit_id, tot_pokok, tot_bunga)
    db.log(c, aktor, "PELUNASAN_DIPERCEPAT", {"kredit_id": kredit_id, "pokok": tot_pokok, "bunga": tot_bunga})
    c.execute("UPDATE kredit SET hari_tunggakan=0 WHERE id=?", (kredit_id,))
    _cek_lunas(c, kredit_id, paksa=True)
    return {"pokok": tot_pokok, "bunga": tot_bunga, "lunas": True, "antrean_disetujui": proses_antrean(c)}


def _terima_dana(c, kredit_id, pokok, bunga):
    c.execute("UPDATE kredit SET allocation = allocation - ?, total_pokok_dibayar = total_pokok_dibayar + ?, "
              "total_bunga_dibayar = total_bunga_dibayar + ? WHERE id=?", (pokok, pokok, bunga, kredit_id))
    c.execute("UPDATE dana_kur SET available = available + ?, total_bunga_diterima = total_bunga_diterima + ? "
              "WHERE id=1", (pokok, bunga))


def _cek_lunas(c, kredit_id, paksa=False) -> bool:
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (kredit_id,))
    sisa = c.execute("SELECT COUNT(*) FROM angsuran WHERE kredit_id=? AND status='BELUM'", (kredit_id,)).fetchone()[0]
    pending = db.row(c, "SELECT id FROM pencairan WHERE kredit_id=? AND status LIKE 'DITUNDA%'", (kredit_id,))
    if k["allocation"] == 0 and sisa == 0 and (paksa or not pending):
        if pending:
            c.execute("UPDATE pencairan SET status='DIBATALKAN', keterangan='Kredit dilunasi' WHERE id=?",
                      (pending["id"],))
        c.execute("UPDATE kredit SET status='LUNAS', tanggal_selesai=?, hari_tunggakan=0 WHERE id=?",
                  (db.today(c), kredit_id))
        wl.release(c, k["debitur_id"], "Kredit LUNAS")
        arsipkan(c, kredit_id, "LUNAS")
        db.notify(c, "LUNAS", "DEBITUR", "Selamat! Kredit KUR Anda telah LUNAS. Riwayat kredit diarsipkan.",
                  k["debitur_id"])
        db.notify(c, "LUNAS", "PETUGAS", f"Kredit #{kredit_id} LUNAS — plafon {rp(k['plafon_max'])} "
                  f"dilepas dari simulasi Banker's.", k["debitur_id"])
        db.log(c, "SISTEM", "KREDIT_LUNAS", {"kredit_id": kredit_id})
        return True
    return False


# =================================================================== arsip
def hitung_skor(jumlah_insiden: int, max_dpd: int, status_akhir: str) -> tuple[int, str]:
    skor = 100 - 4 * jumlah_insiden - min(40, max_dpd // 3)
    if status_akhir == "MACET":
        skor = min(skor, 20)
    skor = max(0, min(100, skor))
    grade = "A" if skor >= 85 else "B" if skor >= 70 else "C" if skor >= 55 else "D" if skor >= 40 else "E"
    return skor, grade


def arsipkan(c, kredit_id: int, status_akhir: str, outstanding=0, klaim=0):
    k = db.row(c, "SELECT * FROM kredit WHERE id=?", (kredit_id,))
    n_ins = c.execute("SELECT COUNT(*) FROM insiden_risiko WHERE kredit_id=?", (kredit_id,)).fetchone()[0]
    skor, grade = hitung_skor(n_ins, k["max_hari_tunggakan"], status_akhir)
    c.execute("INSERT OR REPLACE INTO arsip_kredit(kredit_id,debitur_id,status_akhir,plafon_max,total_dicairkan,"
              "total_pokok_dibayar,outstanding_akhir,klaim_penjaminan,jumlah_insiden,max_hari_tunggakan,skor_kredit,"
              "grade,tanggal_arsip) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (kredit_id, k["debitur_id"], status_akhir, k["plafon_max"], k["total_dicairkan"],
               k["total_pokok_dibayar"], outstanding, klaim, n_ins, k["max_hari_tunggakan"], skor, grade,
               db.today(c)))
    c.execute("UPDATE debitur SET skor_historis=? WHERE id=?", (skor, k["debitur_id"]))
