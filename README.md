# SI-KUR — Sistem Manajemen Kredit Usaha Rakyat Anti Macet
**Banker's Algorithm + LFU** · Kelompok 10 · Sistem Operasi PjBL Kelas F · UIN Maulana Malik Ibrahim Malang

| Peran | Nama | NIM |
|---|---|---|
| Ketua (System Analyst & QA) | Muhammad Ihsan Anshorudin | 240605110199 |
| Desainer (UI/UX & Frontend) | Naufal Mubarok | 240605110041 |
| Programmer (Backend Developer) | Ilham Sinda Firmansyah | 240605110127 |

## Menjalankan
```bash
pip install -r requirements.txt
python run.py --reset        # buat data demo lalu jalankan server
# buka http://127.0.0.1:8000   (dokumentasi API: /docs)
python -m pytest tests -v    # 44 uji otomatis
```

Akun demo: `admin/admin123`, `petugas/petugas123`, debitur `siti`, `bambang`, `indah`, ... dengan password `debitur123`.

## 4 Pilar Sistem Operasi
1. **Manajemen alokasi sumber daya** — Banker's Algorithm (`app/algorithms/bankers.py`): setiap pencairan diuji safe state.
2. **Manajemen memori** — LFU cache slot pengawasan intensif (`app/algorithms/lfu.py`).
3. **Manajemen penyimpanan** — SQLite buku induk siklus kredit + arsip (`app/schema.sql`).
4. **Penanganan deadlock** — Grace period 7 hari, eskalasi/preemption > 90 hari, pemulihan safe state (`app/services/risk_service.py`).

## Struktur
```
app/            backend FastAPI (algoritma, layanan, API, skema, seed)
frontend/       web statis: login, dashboard petugas/admin, portal debitur
tests/          44 uji: unit, integrasi, API, stress-test
data/sikur.db   database demo (dibuat ulang dengan --reset)
docs/           screenshot UI, hasil stress-test (JSON), laporan pytest (XML)
```

Semua nama, NIK, dan nomor HP pada data demo adalah fiktif. Bunga, tenor, dan klaim penjaminan 70% adalah asumsi simulasi.
