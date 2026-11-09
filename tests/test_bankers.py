"""Uji unit Banker's Algorithm (TC-B01 .. TC-B08)."""
import itertools
import random

import pytest

from app.algorithms import bankers as b

# Contoh klasik Silberschatz, Operating System Concepts (5 proses, 3 jenis sumber daya)
AVAIL = [3, 3, 2]
MAX = {0: [7, 5, 3], 1: [3, 2, 2], 2: [9, 0, 2], 3: [2, 2, 2], 4: [4, 3, 3]}
ALLOC = {0: [0, 1, 0], 1: [2, 0, 0], 2: [3, 0, 2], 3: [2, 1, 1], 4: [0, 0, 2]}


def test_B01_contoh_buku_safe():
    r = b.is_safe(AVAIL, MAX, ALLOC)
    assert r.safe
    assert r.sequence == [1, 3, 4, 0, 2]          # <P1, P3, P4, P0, P2>
    assert r.steps[-1].work_after == [10, 5, 7]   # total sumber daya


def test_B02_request_p1_disetujui():
    r = b.request_resources(1, [1, 0, 2], AVAIL, MAX, ALLOC)
    assert r.granted and r.new_available == [2, 3, 0]


def test_B03_request_p4_dana_kurang():
    r = b.request_resources(4, [3, 3, 0], [2, 3, 0], MAX, {**ALLOC, 1: [3, 0, 2]})
    assert r.status == b.WAIT_INSUFFICIENT


def test_B04_request_p0_unsafe():
    r = b.request_resources(0, [0, 2, 0], [2, 3, 0], MAX, {**ALLOC, 1: [3, 0, 2]})
    assert r.status == b.WAIT_UNSAFE and not r.safety.safe


def test_B05_request_melebihi_need():
    r = b.request_resources(3, [1, 1, 1], AVAIL, MAX, ALLOC)  # need P3 = [0,1,1]
    assert r.status == b.ERR_EXCEEDS_NEED


def test_B06_input_tidak_valid():
    with pytest.raises(ValueError):
        b.is_safe([1], {1: [5]}, {1: [6]})        # allocation > max
    with pytest.raises(ValueError):
        b.is_safe([-1], {1: [5]}, {1: [1]})       # available negatif
    with pytest.raises(ValueError):
        b.request_resources(1, [-5], [10], {1: [5]}, {1: [0]})


def test_B07_input_tidak_diubah():
    alloc = {k: list(v) for k, v in ALLOC.items()}
    b.request_resources(1, [1, 0, 2], AVAIL, MAX, alloc)
    assert alloc == ALLOC and AVAIL == [3, 3, 2]


def _brute_safe(avail, mx, al):
    pids = list(mx)
    for perm in itertools.permutations(pids):
        work = list(avail)
        ok = True
        for p in perm:
            need = [m - a for m, a in zip(mx[p], al[p])]
            if all(n <= w for n, w in zip(need, work)):
                work = [w + a for w, a in zip(work, al[p])]
            else:
                ok = False
                break
        if ok:
            return True
    return False


def test_B08_cocok_dengan_brute_force_1000_state_acak():
    rng = random.Random(42)
    unsafe_seen = 0
    for _ in range(1000):
        n, m = rng.randint(1, 5), rng.randint(1, 3)
        mx = {i: [rng.randint(0, 10) for _ in range(m)] for i in range(n)}
        al = {i: [rng.randint(0, mx[i][j]) for j in range(m)] for i in range(n)}
        av = [rng.randint(0, 6) for _ in range(m)]
        r = b.is_safe(av, mx, al)
        assert r.safe == _brute_safe(av, mx, al)
        if r.safe:
            assert sorted(r.sequence) == sorted(mx)
        else:
            unsafe_seen += 1
    assert unsafe_seen > 50  # pastikan kasus unsafe ikut teruji
