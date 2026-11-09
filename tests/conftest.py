import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database as db  # noqa: E402
from app import seed as seed_mod  # noqa: E402
from app.services import kredit_service as ks  # noqa: E402

JT = 1_000_000


@pytest.fixture
def fresh_db(tmp_path):
    """Database kosong (tanpa debitur) dengan pagu 2 M, tanggal 2026-01-01, simulasi perilaku OFF."""
    db.connect(tmp_path / "test.db")
    with db.tx() as c:
        seed_mod.init_db(c, "2026-01-01")
        db.set_param(c, "simulasi_perilaku_debitur", 0)
    yield
    db.connect(tmp_path / "closed.db")


_counter = [0]


def buat_debitur(c, kode="MPR", plafon=None, tenor=12, cair=0, nama=None):
    _counter[0] += 1
    i = _counter[0]
    did = seed_mod.daftar_debitur(c, nama or f"Uji Debitur {i}", f"Usaha {i}", "Malang", kode, None, 9000 + i)
    kat = db.row(c, "SELECT max_plafon FROM kategori_usaha WHERE kode=?", (kode,))
    r = ks.ajukan_kredit(c, did, plafon or kat["max_plafon"], tenor, cair, "pytest")
    return did, r["kredit_id"], r
