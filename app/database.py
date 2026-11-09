"""Koneksi SQLite + helper transaksi (prototype: satu koneksi, dilindungi lock)."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """(Re)buka koneksi global. Dipakai juga oleh tes untuk DB sementara."""
    global _conn
    path = Path(path or config.DB_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL") if str(path) != ":memory:" else None
        schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        _conn.executescript(schema)
    return _conn


def close():
    """Tutup koneksi global (wajib sebelum file DB dihapus, terutama di Windows)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def conn() -> sqlite3.Connection:
    if _conn is None:
        connect()
    return _conn


@contextmanager
def tx():
    """Transaksi atomik + mutual exclusion (critical section)."""
    with _lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


@contextmanager
def read():
    with _lock:
        yield conn()


def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def row(c, sql, args=()):
    r = c.execute(sql, args).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------ parameter
def get_param(c, key):
    r = c.execute("SELECT nilai FROM parameter WHERE kunci=?", (key,)).fetchone()
    if r is None:
        v = config.DEFAULT_PARAMS[key]
        return v
    v = r[0]
    default = config.DEFAULT_PARAMS.get(key)
    if isinstance(default, int):
        return int(float(v))
    return v


def set_param(c, key, value):
    c.execute("INSERT INTO parameter(kunci,nilai) VALUES(?,?) "
              "ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai", (key, str(value)))


def all_params(c) -> dict:
    return {k: get_param(c, k) for k in config.DEFAULT_PARAMS}


def today(c) -> str:
    return get_param(c, "tanggal_sistem")


def log(c, aktor, aksi, detail=None):
    c.execute("INSERT INTO log_aktivitas(tanggal,waktu_nyata,aktor,aksi,detail) VALUES(?,?,?,?,?)",
              (today(c), datetime.now().isoformat(timespec="seconds"), aktor, aksi,
               json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else detail))


def notify(c, tipe, tujuan, pesan, debitur_id=None):
    c.execute("INSERT INTO notifikasi(tanggal,tipe,tujuan,debitur_id,pesan) VALUES(?,?,?,?,?)",
              (today(c), tipe, tujuan, debitur_id, pesan))
