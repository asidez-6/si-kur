"""
Parameter aturan bisnis SI-KUR (ditetapkan oleh Ketua / System Analyst).
Nilai default di sini disalin ke tabel `parameter` saat database dibuat,
sehingga bisa diubah lewat menu Pengaturan tanpa mengubah kode.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SIKUR_DB", BASE_DIR / "data" / "sikur.db"))
FRONTEND_DIR = BASE_DIR / "frontend"

# --- Parameter default (lihat Dokumen Aturan Risiko & Deadlock) ---
DEFAULT_PARAMS = {
    "pagu_dana_kur": 2_000_000_000,      # Total dana KUR yang dikelola unit (Rp)
    "grace_period_hari": 7,               # Masa tenggang keterlambatan
    "pra_eskalasi_hari": 60,              # Peringatan dini sebelum macet
    "eskalasi_hari": 90,                  # > 90 hari tunggakan -> Kredit Macet (NPL)
    "insiden_berlanjut_tiap_hari": 30,    # insiden tambahan tiap 30 hari tunggakan
    "kapasitas_slot_lfu": 5,              # Slot pengawasan intensif
    "lfu_aging_hari": 30,                 # frekuensi turun 1 tiap 30 hari tanpa insiden
    "pemulihan_lancar_hari": 30,          # Pengawasan -> Lancar jika 30 hari bersih
    "persen_penjaminan": 70,              # Klaim penjaminan KUR (simulasi) saat NPL
    "tanggal_sistem": "2026-10-08",       # Jam/tanggal virtual sistem
    "auto_timer_aktif": 0,                # 1 = timer maju 1 hari tiap N detik
    "auto_timer_detik": 10,
    "simulasi_perilaku_debitur": 1,       # 1 = debitur dummy membayar otomatis sesuai profil
}

# Kategori usaha & plafon maksimum (Max pada Banker's Algorithm)
DEFAULT_KATEGORI = [
    # kode, nama, sektor, max_plafon, bunga_tahunan(%), tenor_maks_bulan
    ("SMK", "KUR Super Mikro", "Semua sektor (usaha rintisan)", 10_000_000, 3.0, 36),
    ("MDG", "KUR Mikro Perdagangan", "Perdagangan & Jasa", 50_000_000, 6.0, 36),
    ("MPR", "KUR Mikro Produksi", "Pertanian, Perikanan, Industri Pengolahan", 100_000_000, 6.0, 48),
    ("KDG", "KUR Kecil Perdagangan", "Perdagangan & Jasa", 250_000_000, 6.0, 48),
    ("KPR", "KUR Kecil Produksi", "Pertanian, Perikanan, Industri Pengolahan", 500_000_000, 6.0, 60),
]

SESSION_HOURS = 12
