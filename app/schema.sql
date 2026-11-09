-- =============================================================
-- SI-KUR  — Skema Basis Data (SQLite)
-- Manajemen Penyimpanan: buku induk siklus kredit debitur KUR
-- =============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS parameter (
    kunci       TEXT PRIMARY KEY,
    nilai       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dana_kur (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    pagu                INTEGER NOT NULL,          -- total dana yang dikelola
    available           INTEGER NOT NULL,          -- Available (Banker's)
    total_kerugian_npl  INTEGER NOT NULL DEFAULT 0,-- bagian NPL yang tidak tertutup penjaminan
    total_klaim_penjaminan INTEGER NOT NULL DEFAULT 0,
    total_bunga_diterima   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kategori_usaha (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kode            TEXT UNIQUE NOT NULL,
    nama            TEXT NOT NULL,
    sektor          TEXT NOT NULL,
    max_plafon      INTEGER NOT NULL,              -- Max (Banker's)
    bunga_tahunan   REAL NOT NULL,
    tenor_maks      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pengguna (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    nama            TEXT NOT NULL,
    peran           TEXT NOT NULL CHECK (peran IN ('ADMIN','PETUGAS','DEBITUR')),
    debitur_id      INTEGER REFERENCES debitur(id)
);

CREATE TABLE IF NOT EXISTS sesi (
    token           TEXT PRIMARY KEY,
    pengguna_id     INTEGER NOT NULL REFERENCES pengguna(id) ON DELETE CASCADE,
    kedaluwarsa     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS debitur (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nik             TEXT UNIQUE NOT NULL,
    nama            TEXT NOT NULL,
    no_hp           TEXT,
    alamat          TEXT,
    nama_usaha      TEXT NOT NULL,
    kategori_id     INTEGER NOT NULL REFERENCES kategori_usaha(id),
    tanggal_daftar  TEXT NOT NULL,
    skor_historis   INTEGER,                      -- dari arsip kredit sebelumnya
    profil_simulasi TEXT                          -- DISIPLIN / KADANG_TELAT / BERMASALAH / NULL (manual)
);

-- Satu baris = satu "proses" pada Banker's Algorithm
CREATE TABLE IF NOT EXISTS kredit (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    debitur_id       INTEGER NOT NULL REFERENCES debitur(id),
    plafon_max       INTEGER NOT NULL,            -- Max
    allocation       INTEGER NOT NULL DEFAULT 0,  -- Allocation (pokok outstanding)
    tenor_bulan      INTEGER NOT NULL,
    bunga_tahunan    REAL NOT NULL,
    status           TEXT NOT NULL CHECK (status IN
                     ('MENUNGGU','AKTIF','PENGAWASAN','MACET','LUNAS','DITOLAK')),
    tanggal_pengajuan TEXT NOT NULL,
    tanggal_cair_pertama TEXT,
    tanggal_selesai  TEXT,
    hari_tunggakan   INTEGER NOT NULL DEFAULT 0,
    max_hari_tunggakan INTEGER NOT NULL DEFAULT 0,
    total_dicairkan  INTEGER NOT NULL DEFAULT 0,
    total_pokok_dibayar INTEGER NOT NULL DEFAULT 0,
    total_bunga_dibayar INTEGER NOT NULL DEFAULT 0,
    terakhir_bersih  TEXT                          -- tgl terakhir tunggakan = 0
);
CREATE INDEX IF NOT EXISTS idx_kredit_status ON kredit(status);
CREATE INDEX IF NOT EXISTS idx_kredit_debitur ON kredit(debitur_id);

-- Permintaan pencairan (Request pada Banker's Algorithm)
CREATE TABLE IF NOT EXISTS pencairan (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kredit_id       INTEGER NOT NULL REFERENCES kredit(id),
    jumlah          INTEGER NOT NULL CHECK (jumlah > 0),
    status          TEXT NOT NULL,   -- DISETUJUI / DITUNDA_DANA_KURANG / DITUNDA_UNSAFE / DITOLAK_* / DIBATALKAN
    tanggal_ajuan   TEXT NOT NULL,
    tanggal_proses  TEXT,
    safe_sequence   TEXT,            -- JSON
    keterangan      TEXT,
    diajukan_oleh   TEXT
);
CREATE INDEX IF NOT EXISTS idx_pencairan_status ON pencairan(status);

CREATE TABLE IF NOT EXISTS angsuran (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kredit_id       INTEGER NOT NULL REFERENCES kredit(id),
    pencairan_id    INTEGER NOT NULL REFERENCES pencairan(id),
    angsuran_ke     INTEGER NOT NULL,
    jatuh_tempo     TEXT NOT NULL,
    pokok           INTEGER NOT NULL,
    bunga           INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'BELUM' CHECK (status IN ('BELUM','DIBAYAR','HAPUS_BUKU')),
    tanggal_bayar   TEXT,
    hari_telat      INTEGER NOT NULL DEFAULT 0,
    insiden_dicatat INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_angsuran_kredit ON angsuran(kredit_id, status, jatuh_tempo);

-- Insiden risiko = "page reference" untuk LFU
CREATE TABLE IF NOT EXISTS insiden_risiko (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debitur_id      INTEGER NOT NULL REFERENCES debitur(id),
    kredit_id       INTEGER REFERENCES kredit(id),
    jenis           TEXT NOT NULL,   -- TELAT_BAYAR / TUNGGAKAN_BERLANJUT / USAHA_MENURUN / LAINNYA
    keterangan      TEXT,
    tanggal         TEXT NOT NULL,
    sumber          TEXT NOT NULL DEFAULT 'SISTEM'
);
CREATE INDEX IF NOT EXISTS idx_insiden_debitur ON insiden_risiko(debitur_id);

-- Slot pengawasan intensif (isi cache LFU)
CREATE TABLE IF NOT EXISTS watchlist_slot (
    debitur_id      INTEGER PRIMARY KEY REFERENCES debitur(id),
    frekuensi       INTEGER NOT NULL,
    urutan          INTEGER NOT NULL,   -- urutan LRU di dalam bucket frekuensi
    tanggal_masuk   TEXT NOT NULL,
    insiden_terakhir TEXT NOT NULL,
    aging_terakhir  TEXT
);

CREATE TABLE IF NOT EXISTS watchlist_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal         TEXT NOT NULL,
    aksi            TEXT NOT NULL,      -- MASUK / HIT / EVICT / LEPAS / AGING
    debitur_id      INTEGER NOT NULL,
    frekuensi       INTEGER,
    keterangan      TEXT
);

CREATE TABLE IF NOT EXISTS catatan_komunikasi (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debitur_id      INTEGER NOT NULL REFERENCES debitur(id),
    petugas         TEXT NOT NULL,
    isi             TEXT NOT NULL,
    tanggal         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifikasi (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal         TEXT NOT NULL,
    tipe            TEXT NOT NULL,      -- GRACE / PRA_ESKALASI / ESKALASI / PENCAIRAN / LUNAS / WATCHLIST
    tujuan          TEXT NOT NULL,      -- PETUGAS / COLLECTIONS / DEBITUR
    debitur_id      INTEGER,
    pesan           TEXT NOT NULL,
    dibaca          INTEGER NOT NULL DEFAULT 0
);

-- Arsip siklus kredit (tidak pernah dihapus)
CREATE TABLE IF NOT EXISTS arsip_kredit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kredit_id       INTEGER UNIQUE NOT NULL REFERENCES kredit(id),
    debitur_id      INTEGER NOT NULL REFERENCES debitur(id),
    status_akhir    TEXT NOT NULL,      -- LUNAS / MACET (hapus buku)
    plafon_max      INTEGER NOT NULL,
    total_dicairkan INTEGER NOT NULL,
    total_pokok_dibayar INTEGER NOT NULL,
    outstanding_akhir INTEGER NOT NULL,
    klaim_penjaminan INTEGER NOT NULL DEFAULT 0,
    jumlah_insiden  INTEGER NOT NULL,
    max_hari_tunggakan INTEGER NOT NULL,
    skor_kredit     INTEGER NOT NULL,
    grade           TEXT NOT NULL,
    tanggal_arsip   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS log_aktivitas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal         TEXT NOT NULL,
    waktu_nyata     TEXT NOT NULL,
    aktor           TEXT NOT NULL,
    aksi            TEXT NOT NULL,
    detail          TEXT
);
