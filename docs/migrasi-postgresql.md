# Rencana Migrasi SQLite ke PostgreSQL (SI-KUR)

## 1. Tujuan
Migrasi basis data dari SQLite ke PostgreSQL untuk meningkatkan konkurensi, locking, dan keamanan data produksi.

## 2. Perubahan Koneksi
- `DATABASE_URL` di `.env` diganti ke `postgresql+psycopg://user:pass@host:5432/sikur`.
- Aktifkan connection pooling (`pool_size=10`, `max_overflow=20`).
- Gunakan `SELECT ... FOR UPDATE` pada operasi kredit yang sensitif.

## 3. Skema dan DDL
- Konversi tipe data SQLite ke PostgreSQL (`INTEGER` -> `BIGINT`, `TEXT` -> `VARCHAR`/`TEXT`).
- Tambah index pada `kredit.id`, `nasabah.id`, `transaksi.kredit_id`, `watchlist.nasabah_id`.
- Aktifkan constraint `FOREIGN KEY` dan `CHECK`.

## 4. Migrasi Data
- Ekspor SQLite ke CSV/SQL dump.
- Impor ke PostgreSQL menggunakan `pg_restore` atau script Python.
- Validasi jumlah baris dan checksum data.

## 5. Transaksi dan Concurrency
- Ganti locking SQLite dengan row-level locking PostgreSQL.
- Uji skenario double approval, concurrent payment, dan rollback.

## 6. Konfigurasi Produksi
- Aktifkan SSL (`sslmode=require`).
- Backup harian (`pg_dump`) dan retensi 30 hari.
- Monitoring koneksi dan slow query.

## 7. Rollback
- Simpan snapshot SQLite sebelum cutover.
- Jika gagal, kembali ke `DATABASE_URL` SQLite dan restore snapshot.

## 8. Checklist Uji
- [ ] Semua test API lulus.
- [ ] Coverage main.py tetap >= 88%.
- [ ] Stress test 100 transaksi concurrent lulus.
- [ ] Backup/restore terverifikasi.
