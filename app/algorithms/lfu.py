"""
LFU (Least Frequently Used) Cache — slot pengawasan intensif debitur berisiko.

Analogi Manajemen Memori:
    Frame memori      -> Slot pengawasan intensif (kapasitas terbatas, mis. 5)
    Page              -> Debitur berisiko
    Page reference    -> Insiden risiko (telat bayar, laporan usaha menurun, dst.)
    Frequency         -> Jumlah insiden risiko debitur
    Page fault/evict  -> Slot penuh & debitur baru masuk -> debitur dengan
                         frekuensi insiden PALING JARANG dikeluarkan.

Aturan seri (tie-break): jika beberapa debitur memiliki frekuensi minimum yang
sama, yang dikeluarkan adalah yang insiden terakhirnya PALING LAMA (LRU di
dalam bucket frekuensi yang sama).

Aging (penuaan): untuk mencegah "cache pollution" (debitur lama yang sudah
stabil menumpuk di slot karena frekuensi historisnya besar), frekuensi bisa
diturunkan secara berkala melalui `decay()`.

Semua operasi utama O(1) (kecuali penghitungan ulang min_freq setelah decay /
remove, yang O(jumlah frekuensi berbeda)).
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Hashable


class LFUCache:
    def __init__(self, capacity: int):
        if capacity < 0:
            raise ValueError("Kapasitas tidak boleh negatif")
        self.capacity = capacity
        self.key_freq: dict[Hashable, int] = {}
        self.buckets: dict[int, OrderedDict] = defaultdict(OrderedDict)
        self.min_freq = 0

    # ---------------------------------------------------------------- helpers
    def __contains__(self, key) -> bool:
        return key in self.key_freq

    def __len__(self) -> int:
        return len(self.key_freq)

    def freq(self, key) -> int | None:
        return self.key_freq.get(key)

    def _recompute_min(self) -> None:
        live = [f for f, b in self.buckets.items() if b]
        self.min_freq = min(live) if live else 0

    def _detach(self, key) -> int:
        f = self.key_freq.pop(key)
        bucket = self.buckets[f]
        bucket.pop(key)
        if not bucket:
            del self.buckets[f]
        return f

    def _attach(self, key, f: int) -> None:
        self.key_freq[key] = f
        self.buckets[f][key] = True  # masuk sebagai "paling baru" di bucket

    def victim(self):
        """Debitur yang akan dikeluarkan jika ada page fault (tanpa mengubah state)."""
        if not self.key_freq:
            return None
        self._recompute_min()
        return next(iter(self.buckets[self.min_freq]))

    # ---------------------------------------------------------------- operasi
    def access(self, key, increment: int = 1, initial_freq: int | None = None):
        """Catat satu (atau lebih) insiden untuk `key`.

        - Jika key sudah di slot: frekuensi bertambah (cache hit).
        - Jika belum: dimasukkan dengan frekuensi `initial_freq` (default = increment).
          Jika slot penuh, debitur LFU dikeluarkan lebih dulu.

        Return: (hit: bool, evicted_key | None, evicted_freq | None)
        """
        if self.capacity == 0:
            return False, None, None
        if key in self.key_freq:
            f = self._detach(key)
            self._attach(key, f + increment)
            self._recompute_min()
            return True, None, None

        evicted, evicted_f = None, None
        if len(self.key_freq) >= self.capacity:
            evicted = self.victim()
            evicted_f = self._detach(evicted)
        f0 = initial_freq if initial_freq is not None else increment
        self._attach(key, max(1, f0))
        self._recompute_min()
        return False, evicted, evicted_f

    def remove(self, key) -> int | None:
        """Lepas slot secara paksa (mis. debitur macet/lunas)."""
        if key not in self.key_freq:
            return None
        f = self._detach(key)
        self._recompute_min()
        return f

    def decay(self, key, amount: int = 1, floor: int = 1) -> int | None:
        """Aging: turunkan frekuensi debitur yang lama tidak membuat insiden."""
        if key not in self.key_freq:
            return None
        f = self._detach(key)
        nf = max(floor, f - amount)
        # sisipkan di DEPAN bucket -> dianggap paling "lama" di frekuensi barunya
        self.key_freq[key] = nf
        self.buckets[nf][key] = True
        self.buckets[nf].move_to_end(key, last=False)
        self._recompute_min()
        return nf

    def resize(self, capacity: int) -> list:
        """Ubah kapasitas; kembalikan daftar key yang dikeluarkan."""
        self.capacity = capacity
        out = []
        while len(self.key_freq) > capacity:
            v = self.victim()
            self._detach(v)
            out.append(v)
        self._recompute_min()
        return out

    def items(self) -> list[tuple]:
        """Isi slot terurut: frekuensi tertinggi dulu, lalu paling baru."""
        out = []
        for f in sorted(self.buckets, reverse=True):
            for k in reversed(self.buckets[f]):
                out.append((k, f))
        return out

    def eviction_order(self) -> list:
        """Urutan calon korban (paling dulu dikeluarkan di depan)."""
        out = []
        for f in sorted(self.buckets):
            out.extend(self.buckets[f].keys())
        return out
