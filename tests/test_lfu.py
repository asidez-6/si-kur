"""Uji unit LFU Cache (TC-L01 .. TC-L08)."""
import random

from app.algorithms.lfu import LFUCache


def test_L01_evict_frekuensi_terkecil():
    c = LFUCache(3)
    for k, n in [("A", 3), ("B", 1), ("C", 2)]:
        for _ in range(n):
            c.access(k)
    hit, ev, f = c.access("D")
    assert not hit and ev == "B" and f == 1
    assert set(c.key_freq) == {"A", "C", "D"}


def test_L02_seri_evict_yang_paling_lama():
    c = LFUCache(2)
    c.access("A"); c.access("B")        # sama-sama f=1, A lebih lama
    _, ev, _ = c.access("C")
    assert ev == "A"


def test_L03_hit_menambah_frekuensi():
    c = LFUCache(2)
    c.access("A")
    hit, ev, _ = c.access("A")
    assert hit and ev is None and c.freq("A") == 2


def test_L04_initial_freq_dari_riwayat_insiden():
    c = LFUCache(2)
    c.access("A"); c.access("B"); c.access("B")
    _, ev, _ = c.access("C", initial_freq=5)
    assert ev == "A" and c.freq("C") == 5


def test_L05_remove_dan_decay():
    c = LFUCache(3)
    for _ in range(4):
        c.access("A")
    c.access("B")
    assert c.decay("A", 2) == 2
    assert c.decay("B") == 1          # floor = 1
    assert c.remove("B") == 1 and "B" not in c
    assert c.remove("X") is None


def test_L06_resize_mengeluarkan_lfu():
    c = LFUCache(4)
    for k, n in [("A", 4), ("B", 1), ("C", 3), ("D", 2)]:
        for _ in range(n):
            c.access(k)
    out = c.resize(2)
    assert out == ["B", "D"] and set(c.key_freq) == {"A", "C"}


def test_L07_kapasitas_nol():
    c = LFUCache(0)
    assert c.access("A") == (False, None, None) and len(c) == 0


class RefLFU:
    """Model referensi O(n) untuk membandingkan hasil."""
    def __init__(self, cap):
        self.cap, self.f, self.t, self.clock = cap, {}, {}, 0

    def access(self, k):
        self.clock += 1
        if k in self.f:
            self.f[k] += 1; self.t[k] = self.clock
            return None
        ev = None
        if len(self.f) >= self.cap:
            ev = min(self.f, key=lambda x: (self.f[x], self.t[x]))
            del self.f[ev], self.t[ev]
        self.f[k] = 1; self.t[k] = self.clock
        return ev


def test_L08_cocok_dengan_model_referensi_20000_akses():
    rng = random.Random(7)
    for cap in (1, 3, 5, 10):
        a, r = LFUCache(cap), RefLFU(cap)
        for _ in range(5000):
            k = rng.randint(0, 25)
            _, ev, _ = a.access(k)
            assert ev == r.access(k)
            assert a.key_freq == r.f
