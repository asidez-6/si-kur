"""
Banker's Algorithm (Dijkstra) — implementasi umum untuk m jenis sumber daya.

Dalam SI-KUR sumber daya yang dikelola adalah "Dana KUR" (m = 1, satuan Rupiah),
namun fungsi ditulis dalam bentuk vektor supaya identik dengan rumus di buku
Sistem Operasi (Silberschatz) dan bisa diuji dengan contoh klasik 3 sumber daya.

Pemetaan istilah:
    Process     -> Debitur / fasilitas kredit aktif
    Available   -> Sisa dana KUR yang belum dicairkan
    Max         -> Plafon maksimum yang berpotensi diklaim debitur
    Allocation  -> Pokok kredit yang sudah dicairkan dan belum kembali
    Need        -> Max - Allocation (sisa plafon yang masih bisa diminta)
    Finish      -> Debitur dianggap melunasi -> Allocation kembali ke Available
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Sequence

Vector = list[int]


def _le(a: Sequence[int], b: Sequence[int]) -> bool:
    return all(x <= y for x, y in zip(a, b))


def _add(a: Sequence[int], b: Sequence[int]) -> Vector:
    return [x + y for x, y in zip(a, b)]


def _sub(a: Sequence[int], b: Sequence[int]) -> Vector:
    return [x - y for x, y in zip(a, b)]


@dataclass
class SafetyStep:
    pid: Hashable
    work_before: Vector
    need: Vector
    allocation: Vector
    work_after: Vector


@dataclass
class SafetyResult:
    safe: bool
    sequence: list = field(default_factory=list)
    steps: list[SafetyStep] = field(default_factory=list)
    stuck: list = field(default_factory=list)  # proses yg tidak bisa selesai (jika unsafe)

    def to_dict(self) -> dict:
        return {
            "safe": self.safe,
            "sequence": list(self.sequence),
            "stuck": list(self.stuck),
            "steps": [
                {
                    "pid": s.pid,
                    "work_before": s.work_before,
                    "need": s.need,
                    "allocation": s.allocation,
                    "work_after": s.work_after,
                }
                for s in self.steps
            ],
        }


def _fmt(v: Sequence[int]) -> str:
    if len(v) == 1:
        return "Rp " + f"{v[0]:,}".replace(",", ".")
    return str(list(v))


def compute_need(max_: dict, alloc: dict) -> dict:
    return {p: _sub(max_[p], alloc[p]) for p in max_}


def validate_state(available: Vector, max_: dict, alloc: dict) -> None:
    if set(max_) != set(alloc):
        raise ValueError("Max dan Allocation harus memiliki daftar proses yang sama")
    if any(v < 0 for v in available):
        raise ValueError("Available tidak boleh negatif")
    for p in max_:
        if len(max_[p]) != len(available) or len(alloc[p]) != len(available):
            raise ValueError(f"Dimensi vektor proses {p} tidak sesuai")
        if any(a < 0 for a in alloc[p]):
            raise ValueError(f"Allocation proses {p} negatif")
        if not _le(alloc[p], max_[p]):
            raise ValueError(f"Allocation proses {p} melebihi Max")


def is_safe(available: Vector, max_: dict, alloc: dict, order: Sequence | None = None) -> SafetyResult:
    """Safety Algorithm.

    1. Work = Available, Finish[i] = False
    2. Cari i dengan Finish[i] == False dan Need[i] <= Work
    3. Work = Work + Allocation[i]; Finish[i] = True; ulangi langkah 2
    4. Jika semua Finish[i] == True -> SAFE
    """
    validate_state(available, max_, alloc)
    need = compute_need(max_, alloc)
    pids = list(order) if order is not None else list(max_)
    work = list(available)
    finish = {p: False for p in pids}
    result = SafetyResult(safe=False)

    progressed = True
    while progressed:
        progressed = False
        for p in pids:
            if not finish[p] and _le(need[p], work):
                before = list(work)
                work = _add(work, alloc[p])
                finish[p] = True
                result.sequence.append(p)
                result.steps.append(SafetyStep(p, before, list(need[p]), list(alloc[p]), list(work)))
                progressed = True
    result.safe = all(finish.values())
    result.stuck = [p for p in pids if not finish[p]]
    return result


# Status hasil request
GRANTED = "DISETUJUI"
WAIT_INSUFFICIENT = "DITUNDA_DANA_KURANG"
WAIT_UNSAFE = "DITUNDA_UNSAFE"
ERR_EXCEEDS_NEED = "DITOLAK_MELEBIHI_PLAFON"


@dataclass
class RequestResult:
    status: str
    message: str
    safety: SafetyResult | None = None
    new_available: Vector | None = None

    @property
    def granted(self) -> bool:
        return self.status == GRANTED

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "granted": self.granted,
            "message": self.message,
            "safety": self.safety.to_dict() if self.safety else None,
            "new_available": self.new_available,
        }


def request_resources(pid, request: Vector, available: Vector, max_: dict, alloc: dict) -> RequestResult:
    """Resource-Request Algorithm (tidak mengubah input; hanya mensimulasikan).

    1. Jika Request > Need  -> error (melebihi klaim maksimum)
    2. Jika Request > Available -> tunggu (dana tidak cukup)
    3. Pura-pura alokasikan, jalankan Safety Algorithm:
       SAFE -> setujui ; UNSAFE -> batalkan & tunggu
    """
    if pid not in max_:
        raise KeyError(f"Proses {pid} tidak dikenal")
    if any(r < 0 for r in request):
        raise ValueError("Request tidak boleh negatif")
    need = _sub(max_[pid], alloc[pid])
    if not _le(request, need):
        return RequestResult(ERR_EXCEEDS_NEED,
                             f"Permintaan melebihi sisa plafon (Need = {_fmt(need)}).")
    if not _le(request, available):
        return RequestResult(WAIT_INSUFFICIENT,
                             f"Dana tersedia tidak mencukupi (Available = {_fmt(available)}).")

    trial_available = _sub(available, request)
    trial_alloc = dict(alloc)
    trial_alloc[pid] = _add(alloc[pid], request)
    safety = is_safe(trial_available, max_, trial_alloc)
    if safety.safe:
        return RequestResult(GRANTED, f"State tetap AMAN (sisa Available {_fmt(trial_available)}), "
                                      "pencairan disetujui.", safety, trial_available)
    return RequestResult(WAIT_UNSAFE,
                         f"Jika dicairkan, sisa Available hanya {_fmt(trial_available)} dan tidak ada urutan "
                         f"pelunasan yang menyelesaikan semua debitur -> state UNSAFE (berpotensi deadlock dana). "
                         f"Ditunda.", safety)
