"""Uji integrasi siklus kredit, Grace Period, Eskalasi, LFU & arsip (TC-S01 .. TC-S12)."""
import pytest

from app import database as db
from app.services import kredit_service as ks
from app.services import risk_service as rs
from app.services import watchlist_service as wl
from conftest import JT, buat_debitur


def dana(c):
    return db.row(c, "SELECT * FROM dana_kur WHERE id=1")


def kredit(c, kid):
    return db.row(c, "SELECT * FROM kredit WHERE id=?", (kid,))


def test_S01_pencairan_mengurangi_available_dan_membuat_jadwal(fresh_db):
    with db.tx() as c:
        _, kid, r = buat_debitur(c, "MPR", tenor=12, cair=60 * JT)
        assert r["status"] == "AKTIF"
        assert dana(c)["available"] == 2000 * JT - 60 * JT
        assert kredit(c, kid)["allocation"] == 60 * JT
        ang = db.rows(c, "SELECT * FROM angsuran WHERE kredit_id=?", (kid,))
        assert len(ang) == 12 and sum(a["pokok"] for a in ang) == 60 * JT
        assert ang[0]["jatuh_tempo"] == "2026-01-31"
        assert ks.check_invariant(c)


def test_S02_validasi_plafon_tenor_dan_satu_fasilitas(fresh_db):
    with db.tx() as c:
        did, kid, _ = buat_debitur(c, "SMK", cair=5 * JT)
        with pytest.raises(ks.BisnisError):
            ks.ajukan_kredit(c, did, 5 * JT, 12, 0, "t")            # sudah punya kredit aktif
        with pytest.raises(ks.BisnisError):
            buat_debitur(c, "SMK", plafon=11 * JT)                    # > max kategori
        with pytest.raises(ks.BisnisError):
            buat_debitur(c, "SMK", tenor=99)                          # > tenor maks
        r = ks.ajukan_pencairan(c, kid, 6 * JT, "t")                  # need hanya 5 jt
        assert r["status"] == "DITOLAK_MELEBIHI_PLAFON"


def test_S03_grace_period_tepat_7_hari(fresh_db):
    with db.tx() as c:
        did, kid, _ = buat_debitur(c, "MDG", tenor=6, cair=30 * JT)
        rs.maju_hari(c, 30)                     # 2026-01-31 = jatuh tempo ke-1
        rs.maju_hari(c, 7)                      # telat 7 hari -> masih dalam toleransi
        assert kredit(c, kid)["status"] == "AKTIF"
        assert kredit(c, kid)["hari_tunggakan"] == 7
        rs.maju_hari(c, 1)                      # telat 8 hari -> PENGAWASAN
        assert kredit(c, kid)["status"] == "PENGAWASAN"
        assert db.row(c, "SELECT jenis FROM insiden_risiko WHERE debitur_id=?", (did,))["jenis"] == "TELAT_BAYAR"
        assert did in wl.load_cache(c)[0]


def test_S04_eskalasi_preemption_lebih_dari_90_hari(fresh_db):
    with db.tx() as c:
        did, kid, _ = buat_debitur(c, "MPR", tenor=12, cair=100 * JT)
        avail0 = dana(c)["available"]
        rs.maju_hari(c, 30 + 90)                # tunggakan tepat 90 hari
        assert kredit(c, kid)["status"] == "PENGAWASAN"
        rs.maju_hari(c, 1)                      # 91 hari -> MACET
        k = kredit(c, kid)
        assert k["status"] == "MACET" and k["allocation"] == 0
        d = dana(c)
        assert d["available"] == avail0 + 70 * JT          # klaim penjaminan 70%
        assert d["total_kerugian_npl"] == 30 * JT
        assert ks.check_invariant(c)
        assert did not in wl.load_cache(c)[0]              # slot LFU dilepas
        assert db.row(c, "SELECT * FROM notifikasi WHERE tipe='ESKALASI' AND tujuan='COLLECTIONS'")
        ar = db.row(c, "SELECT * FROM arsip_kredit WHERE kredit_id=?", (kid,))
        assert ar["status_akhir"] == "MACET" and ar["skor_kredit"] <= 20
        assert kid not in ks.banker_state(c)[1]            # keluar dari matriks Banker's
        with pytest.raises(ks.BisnisError):                 # tidak boleh ajukan KUR baru
            ks.ajukan_kredit(c, did, 10 * JT, 12, 0, "t")


def test_S05_insiden_berlanjut_dan_pra_eskalasi(fresh_db):
    with db.tx() as c:
        did, kid, _ = buat_debitur(c, "MPR", tenor=12, cair=50 * JT)
        rs.maju_hari(c, 30 + 60)
        jenis = [r["jenis"] for r in db.rows(c, "SELECT jenis FROM insiden_risiko WHERE debitur_id=?", (did,))]
        assert jenis.count("TUNGGAKAN_BERLANJUT") == 2      # hari ke-30 dan ke-60
        assert jenis.count("TELAT_BAYAR") == 2              # angsuran 1 & 2 lewat grace
        assert db.row(c, "SELECT * FROM notifikasi WHERE tipe='PRA_ESKALASI'")


def test_S06_pemulihan_ke_lancar_setelah_30_hari_bersih(fresh_db):
    with db.tx() as c:
        _, kid, _ = buat_debitur(c, "MDG", tenor=12, cair=24 * JT)
        rs.maju_hari(c, 40)                     # telat 10 hari
        assert kredit(c, kid)["status"] == "PENGAWASAN"
        ks.bayar_angsuran(c, kid, "t")          # lunasi tunggakan
        rs.maju_hari(c, 20)
        ks.bayar_angsuran(c, kid, "t")          # angsuran ke-2 tepat waktu (jt 2026-03-02)
        # insiden terakhir 2026-02-08 (telat 8 hari). Pulih tepat 30 hari kemudian = 2026-03-10
        rs.maju_hari(c, 7)                      # 2026-03-09
        assert kredit(c, kid)["status"] == "PENGAWASAN"
        rs.maju_hari(c, 1)                      # 2026-03-10
        assert kredit(c, kid)["status"] == "AKTIF"


def test_S07_pelunasan_mengembalikan_dana_dan_arsip(fresh_db):
    with db.tx() as c:
        did, kid, _ = buat_debitur(c, "SMK", tenor=3, cair=9 * JT)
        for _ in range(3):
            rs.maju_hari(c, 30)
            ks.bayar_angsuran(c, kid, "t")
        k = kredit(c, kid)
        assert k["status"] == "LUNAS" and k["allocation"] == 0
        assert dana(c)["available"] == 2000 * JT
        ar = db.row(c, "SELECT * FROM arsip_kredit WHERE kredit_id=?", (kid,))
        assert ar["grade"] == "A" and ar["skor_kredit"] == 100
        assert db.row(c, "SELECT skor_historis FROM debitur WHERE id=?", (did,))["skor_historis"] == 100
        assert kid not in ks.banker_state(c)[1]


def test_S08_pelunasan_dipercepat(fresh_db):
    with db.tx() as c:
        _, kid, _ = buat_debitur(c, "MPR", tenor=24, cair=48 * JT)
        rs.maju_hari(c, 31)
        r = ks.lunasi(c, kid, "t")
        assert r["pokok"] == 48 * JT and r["bunga"] == round(48 * JT * 0.06 / 12)  # hanya 1 bunga jatuh tempo
        assert kredit(c, kid)["status"] == "LUNAS"


def test_S09_antrean_unsafe_disetujui_otomatis_saat_dana_kembali(fresh_db):
    with db.tx() as c:
        c.execute("UPDATE dana_kur SET pagu=?, available=?", (300 * JT, 300 * JT))
        _, k1, _ = buat_debitur(c, "KPR", plafon=200 * JT, tenor=2, cair=100 * JT)   # need 100
        _, k2, _ = buat_debitur(c, "KPR", plafon=200 * JT, tenor=12, cair=100 * JT)  # need 100
        _, k3, _ = buat_debitur(c, "KPR", plafon=150 * JT, tenor=12, cair=0)         # need 150
        # Available 100 jt. K3 minta 60 jt -> sisa 40 jt < Need semua debitur (100,100,90) -> UNSAFE
        r = ks.ajukan_pencairan(c, k3, 60 * JT, "t")
        assert r["status"] == "DITUNDA_UNSAFE"
        assert sorted(r["safety"]["stuck"]) == sorted([k1, k2, k3])
        assert dana(c)["available"] == 100 * JT                  # tidak ada dana keluar
        rs.maju_hari(c, 30)
        ks.bayar_angsuran(c, k1, "t")            # 50 jt kembali -> available 150, retry: sisa 90 = need K3 -> SAFE
        p = db.row(c, "SELECT status, safe_sequence FROM pencairan WHERE kredit_id=? ORDER BY id DESC", (k3,))
        assert p["status"] == "DISETUJUI"
        assert kredit(c, k3)["status"] == "AKTIF"
        assert ks.check_invariant(c)


def test_S10_lfu_terintegrasi_evict_saat_slot_penuh(fresh_db):
    with db.tx() as c:
        db.set_param(c, "kapasitas_slot_lfu", 2)
        ids = [buat_debitur(c, "MDG", cair=12 * JT)[0] for _ in range(3)]
        wl.record_incident(c, ids[0], "USAHA_MENURUN", "x")
        wl.record_incident(c, ids[0], "USAHA_MENURUN", "x")
        wl.record_incident(c, ids[1], "USAHA_MENURUN", "x")
        r = wl.record_incident(c, ids[2], "USAHA_MENURUN", "x")
        assert r["evicted"]["debitur_id"] == ids[1]      # frekuensi 1 (terkecil)
        assert set(wl.load_cache(c)[0].key_freq) == {ids[0], ids[2]}
        assert db.row(c, "SELECT * FROM watchlist_log WHERE aksi='EVICT' AND debitur_id=?", (ids[1],))


def test_S11_aging_lfu(fresh_db):
    with db.tx() as c:
        did = buat_debitur(c, "MDG", cair=12 * JT)[0]
        for _ in range(3):
            wl.record_incident(c, did, "USAHA_MENURUN", "x")
        db.set_param(c, "tanggal_sistem", "2026-01-31")
        wl.aging(c)
        assert wl.load_cache(c)[0].freq(did) == 2


def test_S12_batal_pencairan_kredit_menunggu_melepas_max(fresh_db):
    with db.tx() as c:
        c.execute("UPDATE dana_kur SET pagu=?, available=?", (100 * JT, 100 * JT))
        _, kid, r = buat_debitur(c, "MPR", plafon=100 * JT, cair=100 * JT)
        _, kid2, r2 = buat_debitur(c, "MPR", plafon=50 * JT, cair=10 * JT)
        assert r2["status"] == "MENUNGGU"
        assert r2["pencairan"]["status"] == "DITUNDA_DANA_KURANG"
        ks.batalkan_pencairan(c, r2["pencairan"]["pencairan_id"], "t")
        assert kredit(c, kid2)["status"] == "DITOLAK"
        assert kid2 not in ks.banker_state(c)[1]


def test_S13_kerugian_npl_memicu_pembekuan_plafon_agar_tetap_safe(fresh_db):
    """Bug yang ditemukan stress-test X01: kerugian NPL dapat membuat state UNSAFE."""
    from app.algorithms import bankers as b
    with db.tx() as c:
        c.execute("UPDATE dana_kur SET pagu=?, available=?", (400 * JT, 400 * JT))
        db.set_param(c, "persen_penjaminan", 0)           # skenario terburuk: tanpa penjaminan
        _, kmacet, _ = buat_debitur(c, "KPR", plafon=300 * JT, tenor=12, cair=300 * JT)
        _, ka, _ = buat_debitur(c, "KPR", plafon=380 * JT, tenor=12, cair=90 * JT)    # need 290
        for _ in range(4):                                  # K-a disiplin, K-macet tidak bayar
            rs.maju_hari(c, 30)
            ks.bayar_angsuran(c, ka, "t")
        assert kredit(c, kmacet)["status"] == "PENGAWASAN"
        rs.maju_hari(c, 2)                                  # tunggakan > 90 hari -> MACET, rugi 300 jt
        assert kredit(c, kmacet)["status"] == "MACET"
        # tanpa pembekuan: Available 40 + alloc 60 = 100 < Need K-a 320 -> UNSAFE
        assert kredit(c, ka)["plafon_max"] == kredit(c, ka)["allocation"]
        a, m, al, _ = ks.banker_state(c)
        assert b.is_safe(a, m, al).safe and ks.check_invariant(c)
        assert db.row(c, "SELECT * FROM notifikasi WHERE tipe='PEMBEKUAN_PLAFON'")
