"""
Inisialisasi database + data debitur fiktif (dummy) untuk pengujian & demo.

Riwayat dibangkitkan dengan SIMULASI HARIAN sungguhan: mulai 2026-01-05 sistem
"maju" hari demi hari sampai tanggal demo, sehingga status Lancar / Pengawasan /
Macet / Lunas, insiden LFU, dan notifikasi eskalasi terbentuk secara alami
oleh algoritma — bukan diisi manual.

Semua nama, NIK, dan nomor HP di bawah ini FIKTIF.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config
from . import database as db
from .auth import hash_password
from .services import kredit_service as ks
from .services import risk_service as rs
from .services import watchlist_service as wl

START = "2026-01-05"
DEMO_DATE = "2026-10-08"

# (nama, usaha, alamat, kode_kategori, profil, plafon, tenor, cair_awal, hari_mulai)
DEBITUR = [
    ("Siti Aminah", "Warung Sembako Bu Siti", "Lowokwaru, Malang", "MDG", "DISIPLIN", 50, 24, 30, 0),
    ("Bambang Sutrisno", "Tani Jagung Makmur", "Singosari, Kab. Malang", "MPR", "KADANG_TELAT", 100, 24, 80, 3),
    ("Dewi Lestari", "Konveksi Dewi Collection", "Sukun, Malang", "KPR", "DISIPLIN", 500, 36, 250, 5),
    ("Maya Sari", "Laundry Kilat Maya", "Dinoyo, Malang", "SMK", "DISIPLIN", 10, 6, 10, 5),
    ("Teguh Santoso", "Kerupuk Udang Teguh", "Kepanjen, Kab. Malang", "MDG", "DISIPLIN", 50, 12, 30, 8),
    ("Agus Salim", "Bengkel Motor Salim Jaya", "Blimbing, Malang", "KDG", "BERMASALAH", 250, 24, 150, 10),
    ("Rina Wulandari", "Kue Kering Rina", "Klojen, Malang", "SMK", "DISIPLIN", 10, 12, 10, 12),
    ("Joko Prasetyo", "Tambak Lele Barokah", "Pakis, Kab. Malang", "MPR", "BERMASALAH", 100, 24, 90, 15),
    ("Nur Hidayah", "Toko Kelontong Hidayah", "Kedungkandang, Malang", "MDG", "KADANG_TELAT", 50, 24, 40, 20),
    ("Ani Rahmawati", "Jamu Gendong Bu Ani", "Batu", "SMK", "DISIPLIN", 10, 6, 5, 20),
    ("Hendra Gunawan", "Mebel Jati Gunawan", "Turen, Kab. Malang", "KPR", "KADANG_TELAT", 500, 48, 300, 25),
    ("Sri Wahyuni", "Katering Sri Rejeki", "Lowokwaru, Malang", "KDG", "DISIPLIN", 250, 36, 100, 30),
    ("Ahmad Fauzi", "Ternak Ayam Petelur Fauzi", "Lawang, Kab. Malang", "MPR", "BERMASALAH", 100, 24, 80, 35),
    ("Lilis Suryani", "Salon Lilis", "Sukun, Malang", "SMK", "KADANG_TELAT", 10, 12, 8, 40),
    ("Yusuf Habibi", "Distributor Air Galon Habibi", "Blimbing, Malang", "KDG", "KADANG_TELAT", 250, 36, 120, 45),
    ("Fitri Handayani", "Batik Tulis Malangan", "Klojen, Malang", "MPR", "DISIPLIN", 100, 36, 60, 50),
    ("Rudi Hartono", "Bakso Mas Rudi", "Dau, Kab. Malang", "MDG", "BERMASALAH", 50, 24, 40, 151),
    ("Wahyu Nugroho", "Percetakan Nugroho Grafika", "Junrejo, Batu", "KPR", "DISIPLIN", 500, 48, 200, 70),
    ("Eko Saputra", "Sayur Hidroponik Eko", "Bumiaji, Batu", "MPR", "KADANG_TELAT", 100, 24, 50, 90),
    ("Indah Permata", "Butik Indah", "Lowokwaru, Malang", "KDG", "BERMASALAH", 250, 24, 100, 141),
    ("Dodi Kurniawan", "Servis HP Dodi Cell", "Kedungkandang, Malang", "MDG", "KADANG_TELAT", 50, 24, 30, 120),
    ("Putri Ayu", "Kopi Kekinian Ayu", "Sumbersari, Malang", "KDG", "DISIPLIN", 250, 36, 150, 150),
    ("Gilang Ramadhan", "Keripik Tempe Gilang", "Sanan, Malang", "MPR", "KADANG_TELAT", 100, 24, 70, 175),
    ("Wulan Sari", "Florist Wulan", "Klojen, Malang", "MDG", "DISIPLIN", 50, 24, 50, 200),
]

# Top-up (pencairan tambahan) di tengah riwayat: (hari_ke, index_debitur, juta)
TOPUP = [(120, 2, 100), (160, 10, 100), (190, 11, 40), (230, 17, 120), (250, 8, 10)]

# Insiden manual "usaha menurun" + catatan komunikasi: (hari_ke, index, keterangan)
LAPORAN = [
    (140, 1, "Gagal panen sebagian karena hujan deras; omzet turun ±30%."),
    (215, 14, "Satu armada galon rusak, pengiriman berkurang."),
    (260, 22, "Harga kedelai naik, margin keripik menipis."),
]

JT = 1_000_000


def _nik(i: int) -> str:
    return f"3573{(10_000_000 + i * 7_919) % 100_000_000:08d}{i:04d}"


def init_db(c, tanggal: str = DEMO_DATE):
    for k, v in config.DEFAULT_PARAMS.items():
        db.set_param(c, k, v)
    db.set_param(c, "tanggal_sistem", tanggal)
    pagu = config.DEFAULT_PARAMS["pagu_dana_kur"]
    c.execute("INSERT OR REPLACE INTO dana_kur(id,pagu,available) VALUES(1,?,?)", (pagu, pagu))
    for kode, nama, sektor, mx, bunga, tenor in config.DEFAULT_KATEGORI:
        c.execute("INSERT INTO kategori_usaha(kode,nama,sektor,max_plafon,bunga_tahunan,tenor_maks) "
                  "VALUES(?,?,?,?,?,?)", (kode, nama, sektor, mx, bunga, tenor))
    c.execute("INSERT INTO pengguna(username,password_hash,nama,peran) VALUES(?,?,?,?)",
              ("admin", hash_password("admin123"), "Kepala Unit KUR", "ADMIN"))
    c.execute("INSERT INTO pengguna(username,password_hash,nama,peran) VALUES(?,?,?,?)",
              ("petugas", hash_password("petugas123"), "Account Officer (AO)", "PETUGAS"))


def daftar_debitur(c, nama, usaha, alamat, kode, profil, idx) -> int:
    kat = db.row(c, "SELECT id FROM kategori_usaha WHERE kode=?", (kode,))
    did = c.execute("INSERT INTO debitur(nik,nama,no_hp,alamat,nama_usaha,kategori_id,tanggal_daftar,profil_simulasi) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (_nik(idx), nama, f"0812-{3000 + idx * 37:04d}-{1000 + idx * 113:04d}", alamat, usaha,
                     kat["id"], db.today(c), profil)).lastrowid
    uname = nama.split()[0].lower()
    if db.row(c, "SELECT id FROM pengguna WHERE username=?", (uname,)):
        uname = f"{uname}{did}"
    c.execute("INSERT INTO pengguna(username,password_hash,nama,peran,debitur_id) VALUES(?,?,?,?,?)",
              (uname, hash_password("debitur123"), nama, "DEBITUR", did))
    return did


def _buat_ulang_file(path=None):
    """Tutup koneksi, hapus file DB (+ WAL/SHM), lalu buka DB baru yang kosong."""
    import os
    p = path or config.DB_PATH
    db.close()
    if str(p) != ":memory:" and os.path.exists(p):
        os.remove(p)
        for ext in ("-wal", "-shm"):
            if os.path.exists(str(p) + ext):
                os.remove(str(p) + ext)
    db.connect(p)


def kosongkan(path=None, tanggal: str | None = None):
    """Hapus semua data: hanya tersisa parameter, kategori, dana KUR penuh, dan akun admin/petugas."""
    if tanggal is None:
        with db.read() as c:
            tanggal = db.today(c)
    _buat_ulang_file(path)
    with db.tx() as c:
        init_db(c, tanggal)


def seed(path=None, sampai: str = DEMO_DATE, verbose=False):
    _buat_ulang_file(path)
    with db.tx() as c:
        init_db(c, START)
        db.set_param(c, "simulasi_perilaku_debitur", 1)

    total_hari = (date.fromisoformat(sampai) - date.fromisoformat(START)).days
    ids: dict[int, int] = {}
    for hari in range(total_hari + 1):
        with db.tx() as c:
            for i, (nama, usaha, alamat, kode, profil, plafon, tenor, cair, mulai) in enumerate(DEBITUR):
                if mulai == hari:
                    did = daftar_debitur(c, nama, usaha, alamat, kode, profil, i + 1)
                    ids[i] = did
                    r = ks.ajukan_kredit(c, did, plafon * JT, tenor, cair * JT, "petugas")
                    if verbose:
                        print(db.today(c), nama, r["status"], r.get("pencairan", {}).get("status"))
            for h, i, jml in TOPUP:
                if h == hari and i in ids:
                    k = db.row(c, "SELECT id,status FROM kredit WHERE debitur_id=? AND status IN ('AKTIF','MENUNGGU')",
                               (ids[i],))
                    if k:
                        try:
                            r = ks.ajukan_pencairan(c, k["id"], jml * JT, "petugas")
                            if verbose:
                                print(db.today(c), "TOPUP", DEBITUR[i][0], r["status"])
                        except ks.BisnisError as e:
                            if verbose:
                                print("topup gagal", e)
            for h, i, ket in LAPORAN:
                if h == hari and i in ids:
                    k = db.row(c, "SELECT id FROM kredit WHERE debitur_id=? ORDER BY id DESC", (ids[i],))
                    wl.record_incident(c, ids[i], "USAHA_MENURUN", ket, k["id"], "PETUGAS")
                    c.execute("UPDATE kredit SET status='PENGAWASAN' WHERE id=? AND status='AKTIF'", (k["id"],))
                    c.execute("INSERT INTO catatan_komunikasi(debitur_id,petugas,isi,tanggal) VALUES(?,?,?,?)",
                              (ids[i], "Account Officer (AO)", f"Kunjungan lapangan: {ket}", db.today(c)))
            if hari < total_hari:
                rs.maju_hari(c, 1)

    with db.tx() as c:
        # catatan komunikasi tambahan agar buku induk terlihat hidup
        for did, isi in [(1, "Debitur konfirmasi akan bayar tepat waktu, usaha stabil."),
                         (2, "Debitur minta keringanan jadwal karena panen mundur 2 minggu."),
                         (8, "Telepon tidak diangkat 3x, dijadwalkan kunjungan.")]:
            if did in ids.values():
                c.execute("INSERT INTO catatan_komunikasi(debitur_id,petugas,isi,tanggal) VALUES(?,?,?,?)",
                          (did, "Account Officer (AO)", isi, db.today(c)))
        # Dua permintaan pencairan yang tertahan (antrean) untuk demo Banker's
        avail = db.row(c, "SELECT available FROM dana_kur")["available"]
        for nama, jumlah in [("Dewi Lestari", (avail // JT + 25) * JT), ("Wahyu Nugroho", (avail // JT - 2) * JT)]:
            k = db.row(c, "SELECT k.id, k.plafon_max - k.allocation AS need FROM kredit k JOIN debitur d "
                          "ON d.id=k.debitur_id WHERE d.nama=? AND k.status='AKTIF'", (nama,))
            if k and 0 < jumlah <= k["need"]:
                r = ks.ajukan_pencairan(c, k["id"], jumlah, "petugas")
                if verbose:
                    print("ANTREAN", nama, jumlah, r["status"])
        c.execute("UPDATE notifikasi SET dibaca=1 WHERE tanggal < ?",
                  ((date.fromisoformat(sampai) - timedelta(days=14)).isoformat(),))
    return ids


if __name__ == "__main__":
    seed(verbose=True)
    with db.read() as c:
        print(ks.banker_snapshot(c)["safety"]["safe"], db.row(c, "SELECT * FROM dana_kur"))
