"""
STRESS-TEST oleh Ketua (QA): "bertindak sebagai peretas" — skenario pengajuan ekstrem
untuk memastikan Banker's Algorithm tidak pernah salah menghitung safe-state.
Metrik disimpan ke docs/hasil_stress_test.json untuk Laporan Hasil Uji Coba.
"""
import json
import random
import threading
import time
from pathlib import Path

import pytest

from app import database as db
from app.algorithms import bankers as b
from app.services import kredit_service as ks
from app.services import risk_service as rs
from app.services import watchlist_service as wl
from conftest import JT, buat_debitur

METRIK = {}
OUT = Path(__file__).resolve().parent.parent / "docs" / "hasil_stress_test.json"


@pytest.fixture(scope="module", autouse=True)
def simpan_metrik():
    yield
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(METRIK, indent=2, ensure_ascii=False), encoding="utf-8")


def state_aman(c):
    a, m, al, _ = ks.banker_state(c)
    return b.is_safe(a, m, al).safe


KODE = ["SMK", "MDG", "MPR", "KDG", "KPR"]


def test_X01_3000_operasi_acak_invariant_dan_safe_selalu_terjaga(fresh_db):
    rng = random.Random(2026)
    hitung = {"pencairan": 0, "DISETUJUI": 0, "DITUNDA_DANA_KURANG": 0, "DITUNDA_UNSAFE": 0,
              "DITOLAK_MELEBIHI_PLAFON": 0, "bayar": 0, "maju_hari": 0, "debitur_baru": 0, "error_bisnis": 0,
              "cek_invariant": 0}
    t0 = time.perf_counter()
    with db.tx() as c:
        for i in range(3000):
            op = rng.random()
            try:
                if op < 0.12:
                    buat_debitur(c, rng.choice(KODE), tenor=rng.choice([3, 6, 12]), cair=0)
                    hitung["debitur_baru"] += 1
                elif op < 0.62:
                    ks_ = db.rows(c, "SELECT id, plafon_max-allocation need FROM kredit WHERE status IN ('MENUNGGU','AKTIF')")
                    if ks_:
                        k = rng.choice(ks_)
                        jml = rng.choice([1, rng.randint(1, max(1, k["need"])), k["need"] + rng.randint(1, 50 * JT),
                                          rng.randint(1, 600 * JT)])
                        if jml > 0 and not db.row(c, "SELECT id FROM pencairan WHERE kredit_id=? AND status LIKE 'DITUNDA%'", (k["id"],)):
                            r = ks.ajukan_pencairan(c, k["id"], jml, "stress")
                            hitung["pencairan"] += 1
                            hitung[r["status"]] += 1
                            if r["granted"]:
                                assert r["safety"]["safe"]
                elif op < 0.85:
                    ks_ = db.rows(c, "SELECT id FROM kredit WHERE status IN ('AKTIF','PENGAWASAN')")
                    if ks_:
                        ks.bayar_angsuran(c, rng.choice(ks_)["id"], "stress")
                        hitung["bayar"] += 1
                else:
                    rs.maju_hari(c, rng.randint(1, 20))
                    hitung["maju_hari"] += 1
            except ks.BisnisError:
                hitung["error_bisnis"] += 1
            assert ks.check_invariant(c), f"invariant dana rusak pada operasi {i}"
            hitung["pembekuan_plafon"] = c.execute("SELECT COUNT(*) FROM log_aktivitas WHERE aksi='PEMBEKUAN_PLAFON'").fetchone()[0]
            assert state_aman(c), f"state UNSAFE pada operasi {i}"
            assert db.row(c, "SELECT available FROM dana_kur")["available"] >= 0
            assert len(wl.load_cache(c)[0]) <= db.get_param(c, "kapasitas_slot_lfu")
            hitung["cek_invariant"] += 1
        st = {r["status"]: r["n"] for r in db.rows(c, "SELECT status, COUNT(*) n FROM kredit GROUP BY status")}
    hitung["status_akhir_kredit"] = st
    hitung["durasi_detik"] = round(time.perf_counter() - t0, 2)
    METRIK["X01_operasi_acak"] = hitung
    assert hitung["DITUNDA_UNSAFE"] > 0 and hitung["DISETUJUI"] > 100


def test_X02_bank_run_semua_debitur_minta_need_penuh_bersamaan(fresh_db):
    with db.tx() as c:
        kids = [buat_debitur(c, KODE[i % 5], tenor=6, cair=0)[1] for i in range(40)]
        total_need = c.execute("SELECT SUM(plafon_max) FROM kredit").fetchone()[0]
        hasil = {}
        for k in kids:
            need = db.row(c, "SELECT plafon_max FROM kredit WHERE id=?", (k,))["plafon_max"]
            r = ks.ajukan_pencairan(c, k, need, "bank-run")
            hasil[r["status"]] = hasil.get(r["status"], 0) + 1
            assert state_aman(c) and ks.check_invariant(c)
        avail = db.row(c, "SELECT available FROM dana_kur")["available"]
        antre0 = c.execute("SELECT COUNT(*) FROM pencairan WHERE status LIKE 'DITUNDA%'").fetchone()[0]
        # waktu berjalan, semua yang sudah cair membayar disiplin -> antrean terkuras
        for _ in range(14):
            rs.maju_hari(c, 30)
            for k in db.rows(c, "SELECT id FROM kredit WHERE status IN ('AKTIF','PENGAWASAN')"):
                while db.row(c, "SELECT id FROM angsuran WHERE kredit_id=? AND status='BELUM' AND jatuh_tempo<=?",
                             (k["id"], db.today(c))):
                    ks.bayar_angsuran(c, k["id"], "bank-run")
            assert state_aman(c) and ks.check_invariant(c)
        antre1 = c.execute("SELECT COUNT(*) FROM pencairan WHERE status LIKE 'DITUNDA%'").fetchone()[0]
        disetujui = c.execute("SELECT COUNT(*) FROM pencairan WHERE status='DISETUJUI'").fetchone()[0]
    METRIK["X02_bank_run"] = {"debitur": 40, "total_klaim_max": total_need, "pagu": 2000 * JT,
                              "hasil_awal": hasil, "available_setelah_gelombang": avail,
                              "antrean_awal": antre0, "antrean_setelah_14_bulan": antre1,
                              "total_disetujui_akhir": disetujui}
    assert antre0 > 0 and antre1 == 0 and disetujui == 40


def test_X03_concurrency_30_thread_berebut_dana(fresh_db):
    with db.tx() as c:
        c.execute("UPDATE dana_kur SET pagu=?, available=?", (500 * JT, 500 * JT))
        kids = [buat_debitur(c, "KDG", tenor=12, cair=0)[1] for _ in range(30)]
    hasil, lock = [], threading.Lock()

    def worker(k):
        with db.tx() as c:
            r = ks.ajukan_pencairan(c, k, 100 * JT, "thread")
        with lock:
            hasil.append(r["status"])
    th = [threading.Thread(target=worker, args=(k,)) for k in kids]
    [t.start() for t in th]
    [t.join() for t in th]
    with db.read() as c:
        alloc = c.execute("SELECT SUM(allocation) FROM kredit").fetchone()[0]
        assert alloc <= 500 * JT and ks.check_invariant(c) and state_aman(c)
    METRIK["X03_concurrency"] = {"thread": 30, "permintaan_per_thread": 100 * JT, "pagu": 500 * JT,
                                 "disetujui": hasil.count("DISETUJUI"),
                                 "ditunda": len(hasil) - hasil.count("DISETUJUI"), "total_allocation": alloc}
    assert hasil.count("DISETUJUI") >= 1


def test_X04_gagal_bayar_massal_semua_tereskalasi(fresh_db):
    with db.tx() as c:
        for i in range(30):
            buat_debitur(c, KODE[i % 5], tenor=12, cair=[5, 25, 50, 90, 150][i % 5] * JT)  # total 1,92 M < pagu
        out_total = c.execute("SELECT SUM(allocation) FROM kredit").fetchone()[0]
        r = rs.maju_hari(c, 125)
        macet = c.execute("SELECT COUNT(*) FROM kredit WHERE status='MACET'").fetchone()[0]
        d = db.row(c, "SELECT * FROM dana_kur")
        assert macet == 30 and ks.check_invariant(c)
        assert d["total_kerugian_npl"] + d["total_klaim_penjaminan"] == out_total
        assert len(wl.load_cache(c)[0]) == 0
        n_notif = c.execute("SELECT COUNT(*) FROM notifikasi WHERE tipe='ESKALASI' AND tujuan='COLLECTIONS'").fetchone()[0]
    METRIK["X04_gagal_bayar_massal"] = {"debitur": 30, "outstanding": out_total, "macet": macet,
                                        "klaim_penjaminan": d["total_klaim_penjaminan"],
                                        "kerugian": d["total_kerugian_npl"], "available_akhir": d["available"],
                                        "notifikasi_collections": n_notif, "insiden": r["insiden"]}
    assert n_notif == 30


def test_X05_input_ekstrem_tidak_merusak_sistem(fresh_db):
    kasus = {}
    with db.tx() as c:
        _, kid, _ = buat_debitur(c, "KPR", tenor=12, cair=0)
        for nama, jml in [("nol", 0), ("negatif", -5 * JT), ("1_rupiah", 1), ("sangat_besar", 10 ** 15),
                          ("tepat_need", 500 * JT - 1)]:
            try:
                r = ks.ajukan_pencairan(c, kid, jml, "x")
                kasus[nama] = r["status"]
                if r["status"].startswith("DITUNDA"):
                    pid = r["pencairan_id"]
                    c.execute("UPDATE pencairan SET status='DIBATALKAN' WHERE id=?", (pid,))
            except ks.BisnisError as e:
                kasus[nama] = "DITOLAK: " + str(e)
            assert ks.check_invariant(c) and state_aman(c)
        try:
            ks.ajukan_pencairan(c, 99999, 1, "x")
        except ks.BisnisError as e:
            kasus["kredit_tidak_ada"] = "DITOLAK: " + str(e)
        try:
            ks.ajukan_kredit(c, 99999, 1, 1, 0, "x")
        except ks.BisnisError as e:
            kasus["debitur_tidak_ada"] = "DITOLAK: " + str(e)
    METRIK["X05_input_ekstrem"] = kasus
    assert kasus["nol"].startswith("DITOLAK") and kasus["negatif"].startswith("DITOLAK")
    assert kasus["sangat_besar"] == "DITOLAK_MELEBIHI_PLAFON"
    assert kasus["1_rupiah"] == "DISETUJUI"


def test_X06_performa_safety_algorithm():
    rng = random.Random(1)
    hasil = {}
    for n in (100, 500, 1000, 2000):
        mx = {i: [rng.randint(1, 500) * JT] for i in range(n)}
        al = {i: [rng.randint(0, mx[i][0])] for i in range(n)}
        t0 = time.perf_counter()
        r = b.is_safe([200 * JT], mx, al)
        hasil[f"{n}_debitur_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    METRIK["X06_performa"] = hasil
    assert hasil["1000_debitur_ms"] < 2000


def test_X07_lfu_kapasitas_tidak_pernah_terlampaui(fresh_db):
    rng = random.Random(3)
    with db.tx() as c:
        ids = [buat_debitur(c, "MDG", cair=10 * JT)[0] for _ in range(25)]
        evict = 0
        for _ in range(400):
            r = wl.record_incident(c, rng.choice(ids), "LAINNYA", "stress")
            evict += 1 if r["evicted"] else 0
            assert len(wl.load_cache(c)[0]) <= 5
        cache = wl.load_cache(c)[0]
        # isi slot = 5 debitur dengan frekuensi terbesar? (LFU tidak menjamin, tapi minimal freq slot >= 1)
        assert all(f >= 1 for f in cache.key_freq.values())
    METRIK["X07_lfu"] = {"insiden": 400, "debitur": 25, "kapasitas": 5, "jumlah_evict": evict,
                         "isi_akhir": dict(sorted(cache.key_freq.items(), key=lambda x: -x[1]))}
