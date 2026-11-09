"""Persistensi cache LFU (slot pengawasan intensif) ke tabel watchlist_slot."""
from __future__ import annotations

from datetime import date

from .. import database as db
from ..algorithms.lfu import LFUCache


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def load_cache(c) -> tuple[LFUCache, dict]:
    cap = db.get_param(c, "kapasitas_slot_lfu")
    cache = LFUCache(cap)
    meta = {}
    for r in db.rows(c, "SELECT * FROM watchlist_slot ORDER BY urutan ASC"):
        cache.key_freq[r["debitur_id"]] = r["frekuensi"]
        cache.buckets[r["frekuensi"]][r["debitur_id"]] = True
        meta[r["debitur_id"]] = r
    cache._recompute_min()
    return cache, meta


def save_cache(c, cache: LFUCache, meta: dict) -> None:
    keys = set(cache.key_freq)
    for old in [k for k in meta if k not in keys]:
        c.execute("DELETE FROM watchlist_slot WHERE debitur_id=?", (old,))
    for idx, k in enumerate(cache.eviction_order()):
        m = meta.get(k, {})
        c.execute(
            "INSERT INTO watchlist_slot(debitur_id,frekuensi,urutan,tanggal_masuk,insiden_terakhir,aging_terakhir) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(debitur_id) DO UPDATE SET frekuensi=excluded.frekuensi, "
            "urutan=excluded.urutan, insiden_terakhir=excluded.insiden_terakhir, aging_terakhir=excluded.aging_terakhir",
            (k, cache.key_freq[k], idx, m.get("tanggal_masuk") or db.today(c),
             m.get("insiden_terakhir") or db.today(c), m.get("aging_terakhir")))


def _wlog(c, aksi, debitur_id, freq, ket=None):
    c.execute("INSERT INTO watchlist_log(tanggal,aksi,debitur_id,frekuensi,keterangan) VALUES(?,?,?,?,?)",
              (db.today(c), aksi, debitur_id, freq, ket))


def _nama(c, debitur_id):
    r = db.row(c, "SELECT nama FROM debitur WHERE id=?", (debitur_id,))
    return r["nama"] if r else f"#{debitur_id}"


def record_incident(c, debitur_id: int, jenis: str, keterangan: str = "", kredit_id=None,
                    sumber: str = "SISTEM") -> dict:
    """Catat insiden risiko lalu perbarui cache LFU (page reference)."""
    today = db.today(c)
    c.execute("INSERT INTO insiden_risiko(debitur_id,kredit_id,jenis,keterangan,tanggal,sumber) VALUES(?,?,?,?,?,?)",
              (debitur_id, kredit_id, jenis, keterangan, today, sumber))
    total = c.execute("SELECT COUNT(*) FROM insiden_risiko WHERE debitur_id=?", (debitur_id,)).fetchone()[0]

    cache, meta = load_cache(c)
    hit, evicted, evicted_f = cache.access(debitur_id, increment=1, initial_freq=total)
    m = dict(meta.get(debitur_id, {}))
    m["insiden_terakhir"] = today
    m["aging_terakhir"] = None
    if not hit:
        m["tanggal_masuk"] = today
    meta[debitur_id] = m
    save_cache(c, cache, meta)

    result = {"hit": hit, "frekuensi": cache.freq(debitur_id), "evicted": None}
    if hit:
        _wlog(c, "HIT", debitur_id, cache.freq(debitur_id), f"Insiden {jenis}")
    else:
        _wlog(c, "MASUK", debitur_id, cache.freq(debitur_id), f"Masuk slot karena insiden {jenis}")
        db.notify(c, "WATCHLIST", "PETUGAS",
                  f"{_nama(c, debitur_id)} masuk slot pengawasan intensif (frekuensi {cache.freq(debitur_id)}).",
                  debitur_id)
    if evicted is not None:
        _wlog(c, "EVICT", evicted, evicted_f,
              f"Dikeluarkan (LFU) untuk memberi ruang bagi {_nama(c, debitur_id)}")
        db.notify(c, "WATCHLIST", "PETUGAS",
                  f"{_nama(c, evicted)} dikeluarkan dari slot intensif (frekuensi {evicted_f}, paling jarang) "
                  f"-> kembali ke pemantauan reguler.", evicted)
        result["evicted"] = {"debitur_id": evicted, "frekuensi": evicted_f}
    return result


def release(c, debitur_id: int, alasan: str) -> int | None:
    cache, meta = load_cache(c)
    f = cache.remove(debitur_id)
    if f is not None:
        save_cache(c, cache, meta)
        _wlog(c, "LEPAS", debitur_id, f, alasan)
    return f


def aging(c) -> list[int]:
    """Turunkan frekuensi debitur yang tidak membuat insiden selama N hari."""
    n = db.get_param(c, "lfu_aging_hari")
    if n <= 0:
        return []
    today = db.today(c)
    cache, meta = load_cache(c)
    changed = []
    for k, m in list(meta.items()):
        ref = m.get("aging_terakhir") or m["insiden_terakhir"]
        if _days(ref, today) >= n and cache.freq(k) > 1:
            nf = cache.decay(k)
            m = dict(m)
            m["aging_terakhir"] = today
            meta[k] = m
            changed.append(k)
            _wlog(c, "AGING", k, nf, f"{n} hari tanpa insiden baru")
        elif _days(ref, today) >= n:
            m = dict(m)
            m["aging_terakhir"] = today
            meta[k] = m
    if changed or meta:
        save_cache(c, cache, meta)
    return changed


def resize(c, capacity: int) -> list[int]:
    db.set_param(c, "kapasitas_slot_lfu", capacity)
    cache, meta = load_cache(c)
    out = cache.resize(capacity)
    save_cache(c, cache, meta)
    for k in out:
        _wlog(c, "EVICT", k, None, f"Kapasitas slot dikurangi menjadi {capacity}")
    return out


def snapshot(c) -> dict:
    cache, meta = load_cache(c)
    order = cache.eviction_order()
    slots = []
    for k, f in cache.items():
        d = db.row(c, """SELECT d.id, d.nama, d.nama_usaha, k.status, k.hari_tunggakan, k.allocation
                         FROM debitur d LEFT JOIN kredit k ON k.debitur_id=d.id
                              AND k.status IN ('MENUNGGU','AKTIF','PENGAWASAN')
                         WHERE d.id=?""", (k,))
        slots.append({**(d or {"id": k}), "frekuensi": f,
                      "tanggal_masuk": meta[k]["tanggal_masuk"],
                      "insiden_terakhir": meta[k]["insiden_terakhir"],
                      "posisi_evict": order.index(k) + 1})
    return {"kapasitas": cache.capacity, "terisi": len(cache),
            "calon_evict": cache.victim(), "slot": slots}
