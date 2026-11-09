"""
SI-KUR — REST API (FastAPI)
Jalankan:  python run.py      lalu buka http://127.0.0.1:8000
Dokumentasi API interaktif: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, config
from . import database as db
from .services import kredit_service as ks
from .services import risk_service as rs
from .services import watchlist_service as wl


# ======================================================== timer otomatis
async def _timer_loop():
    last = time.monotonic()
    while True:
        await asyncio.sleep(1)
        try:
            with db.read() as c:
                aktif = db.get_param(c, "auto_timer_aktif")
                detik = max(1, db.get_param(c, "auto_timer_detik"))
            if aktif and time.monotonic() - last >= detik:
                with db.tx() as c:
                    rs.maju_hari(c, 1)
                last = time.monotonic()
            elif not aktif:
                last = time.monotonic()
        except Exception as e:  # timer tidak boleh mati
            print("[timer] error:", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    with db.read() as c:
        kosong = c.execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0
    if kosong:
        from .seed import seed
        print("[SI-KUR] Database kosong -> membuat data demo ...")
        seed()
    task = asyncio.create_task(_timer_loop())
    yield
    task.cancel()


app = FastAPI(title="SI-KUR API", version="1.0.0", lifespan=lifespan,
              description="Sistem Manajemen Kredit Usaha Rakyat Anti Macet — Banker's Algorithm + LFU")


@app.middleware("http")
async def tanpa_cache_frontend(request: Request, call_next):
    """Paksa browser memvalidasi ulang file frontend agar perubahan JS/CSS langsung terlihat."""
    resp = await call_next(request)
    if not request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.exception_handler(ks.BisnisError)
async def bisnis_error(_: Request, e: ks.BisnisError):
    return JSONResponse(status_code=400, content={"detail": str(e)})


# ================================================================ schemas
class LoginIn(BaseModel):
    username: str
    password: str


class DebiturIn(BaseModel):
    nik: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    nama: str = Field(min_length=3)
    no_hp: str = ""
    alamat: str = ""
    nama_usaha: str = Field(min_length=3)
    kategori_id: int
    plafon: Optional[int] = None          # default = max plafon kategori
    tenor_bulan: int = 24
    pencairan_awal: int = 0
    buat_akun: bool = True


class KreditIn(BaseModel):
    debitur_id: int
    plafon: Optional[int] = None
    tenor_bulan: int = 24
    pencairan_awal: int = 0


class JumlahIn(BaseModel):
    jumlah: int = Field(gt=0)


class InsidenIn(BaseModel):
    jenis: str = "USAHA_MENURUN"
    keterangan: str = Field(min_length=3)


class CatatanIn(BaseModel):
    isi: str = Field(min_length=3)


class MajuIn(BaseModel):
    hari: int = Field(1, ge=1, le=400)


class BayarIn(BaseModel):
    jumlah_angsuran: int = Field(1, ge=1, le=60)


class KapasitasIn(BaseModel):
    kapasitas: int = Field(ge=1, le=50)


class KategoriIn(BaseModel):
    nama: Optional[str] = None
    max_plafon: Optional[int] = Field(None, gt=0)
    bunga_tahunan: Optional[float] = Field(None, ge=0)
    tenor_maks: Optional[int] = Field(None, ge=1)


# ================================================================== auth
@app.post("/api/auth/login", tags=["Auth"])
def login(body: LoginIn):
    r = auth.login(body.username, body.password)
    if not r:
        raise HTTPException(401, "Username atau password salah")
    return r


@app.post("/api/auth/logout", tags=["Auth"])
def logout(user=Depends(auth.current_user)):
    auth.logout(user["token"])
    return {"ok": True}


@app.get("/api/auth/me", tags=["Auth"])
def me(user=Depends(auth.current_user)):
    return user


# ============================================================= dashboard
@app.get("/api/dashboard", tags=["Dashboard"])
def dashboard(user=Depends(auth.staff)):
    with db.read() as c:
        snap = ks.banker_snapshot(c)
        status = {r["status"]: r["n"] for r in db.rows(c, "SELECT status, COUNT(*) n FROM kredit GROUP BY status")}
        outstanding_pengawasan = c.execute(
            "SELECT COALESCE(SUM(allocation),0) FROM kredit WHERE status='PENGAWASAN'").fetchone()[0]
        total_cair = c.execute("SELECT COALESCE(SUM(total_dicairkan),0) FROM kredit").fetchone()[0]
        npl_pokok = c.execute("SELECT COALESCE(SUM(outstanding_akhir),0) FROM arsip_kredit "
                              "WHERE status_akhir='MACET'").fetchone()[0]
        antrean = db.rows(c, "SELECT p.*, d.nama FROM pencairan p JOIN kredit k ON k.id=p.kredit_id "
                             "JOIN debitur d ON d.id=k.debitur_id WHERE p.status LIKE 'DITUNDA%' ORDER BY p.id")
        notif = c.execute("SELECT COUNT(*) FROM notifikasi WHERE dibaca=0 AND tujuan!='DEBITUR'").fetchone()[0]
        tren = db.rows(c, "SELECT substr(tanggal,1,7) bulan, jenis, COUNT(*) n FROM insiden_risiko "
                          "GROUP BY bulan, jenis ORDER BY bulan")
        dana = db.row(c, "SELECT * FROM dana_kur WHERE id=1")
        return {
            "tanggal_sistem": db.today(c),
            "dana": dana,
            "banker": {k: snap[k] for k in ("available", "pagu", "total_allocation", "total_need")},
            "safe": snap["safety"]["safe"],
            "safe_sequence": snap["safety"]["sequence"],
            "status_kredit": status,
            "outstanding_pengawasan": outstanding_pengawasan,
            "total_dicairkan": total_cair,
            "npl_ratio": round(npl_pokok / total_cair * 100, 2) if total_cair else 0,
            "antrean": antrean,
            "notif_belum_dibaca": notif,
            "watchlist": wl.snapshot(c),
            "tren_insiden": tren,
            "invariant_ok": ks.check_invariant(c),
        }


# ============================================================ Banker's
@app.get("/api/bankers/state", tags=["Banker's Algorithm"])
def bankers_state(user=Depends(auth.staff)):
    with db.read() as c:
        return ks.banker_snapshot(c)


@app.post("/api/bankers/simulasi/{kredit_id}", tags=["Banker's Algorithm"])
def bankers_simulasi(kredit_id: int, body: JumlahIn, user=Depends(auth.staff)):
    with db.read() as c:
        return ks.simulasi_pencairan(c, kredit_id, body.jumlah)


# ============================================================== kategori
@app.get("/api/kategori", tags=["Master"])
def kategori(user=Depends(auth.current_user)):
    with db.read() as c:
        return db.rows(c, "SELECT * FROM kategori_usaha ORDER BY max_plafon")


@app.put("/api/kategori/{kid}", tags=["Master"])
def ubah_kategori(kid: int, body: KategoriIn, user=Depends(auth.admin)):
    with db.tx() as c:
        for f, v in body.model_dump(exclude_none=True).items():
            c.execute(f"UPDATE kategori_usaha SET {f}=? WHERE id=?", (v, kid))
        db.log(c, user["username"], "UBAH_KATEGORI", {"id": kid, **body.model_dump(exclude_none=True)})
        return db.row(c, "SELECT * FROM kategori_usaha WHERE id=?", (kid,))


# =============================================================== debitur
_DEB_SQL = """
SELECT d.*, kat.nama AS kategori, kat.kode AS kode_kategori, kat.max_plafon,
       k.id AS kredit_id, k.status, k.plafon_max, k.allocation, k.hari_tunggakan, k.tenor_bulan,
       (SELECT COUNT(*) FROM insiden_risiko i WHERE i.debitur_id=d.id) AS jumlah_insiden,
       (SELECT frekuensi FROM watchlist_slot w WHERE w.debitur_id=d.id) AS frekuensi_lfu
FROM debitur d
JOIN kategori_usaha kat ON kat.id=d.kategori_id
LEFT JOIN kredit k ON k.id = (SELECT id FROM kredit WHERE debitur_id=d.id ORDER BY
     CASE WHEN status IN ('MENUNGGU','AKTIF','PENGAWASAN') THEN 0 ELSE 1 END, id DESC LIMIT 1)
"""


@app.get("/api/debitur", tags=["Debitur"])
def list_debitur(status: Optional[str] = None, q: Optional[str] = None, user=Depends(auth.staff)):
    sql, args = _DEB_SQL + " WHERE 1=1", []
    if status:
        sql += " AND k.status=?"
        args.append(status)
    if q:
        sql += " AND (d.nama LIKE ? OR d.nama_usaha LIKE ? OR d.nik LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY CASE k.status WHEN 'MACET' THEN 0 WHEN 'PENGAWASAN' THEN 1 WHEN 'MENUNGGU' THEN 2 " \
           "WHEN 'AKTIF' THEN 3 ELSE 4 END, k.hari_tunggakan DESC, d.nama"
    with db.read() as c:
        return db.rows(c, sql, args)


def _detail(c, did: int) -> dict:
    d = db.row(c, _DEB_SQL + " WHERE d.id=?", (did,))
    if not d:
        raise HTTPException(404, "Debitur tidak ditemukan")
    d["kredit"] = db.rows(c, "SELECT * FROM kredit WHERE debitur_id=? ORDER BY id DESC", (did,))
    kid = d["kredit_id"]
    d["angsuran"] = db.rows(c, "SELECT * FROM angsuran WHERE kredit_id=? ORDER BY jatuh_tempo, id", (kid,)) if kid else []
    d["pencairan"] = db.rows(c, "SELECT p.* FROM pencairan p JOIN kredit k ON k.id=p.kredit_id "
                                "WHERE k.debitur_id=? ORDER BY p.id DESC", (did,))
    d["insiden"] = db.rows(c, "SELECT * FROM insiden_risiko WHERE debitur_id=? ORDER BY id DESC", (did,))
    d["catatan"] = db.rows(c, "SELECT * FROM catatan_komunikasi WHERE debitur_id=? ORDER BY id DESC", (did,))
    d["arsip"] = db.rows(c, "SELECT * FROM arsip_kredit WHERE debitur_id=? ORDER BY id DESC", (did,))
    d["notifikasi"] = db.rows(c, "SELECT * FROM notifikasi WHERE debitur_id=? ORDER BY id DESC LIMIT 30", (did,))
    d["watchlist_log"] = db.rows(c, "SELECT * FROM watchlist_log WHERE debitur_id=? ORDER BY id DESC", (did,))
    d["akun"] = db.row(c, "SELECT username FROM pengguna WHERE debitur_id=?", (did,))
    return d


@app.get("/api/debitur/{did}", tags=["Debitur"])
def detail_debitur(did: int, user=Depends(auth.staff)):
    with db.read() as c:
        return _detail(c, did)


@app.post("/api/debitur", tags=["Debitur"])
def tambah_debitur(body: DebiturIn, user=Depends(auth.staff)):
    from .seed import daftar_debitur  # noqa
    with db.tx() as c:
        kat = db.row(c, "SELECT * FROM kategori_usaha WHERE id=?", (body.kategori_id,))
        if not kat:
            raise ks.BisnisError("Kategori tidak valid")
        if db.row(c, "SELECT id FROM debitur WHERE nik=?", (body.nik,)):
            raise ks.BisnisError("NIK sudah terdaftar")
        did = c.execute("INSERT INTO debitur(nik,nama,no_hp,alamat,nama_usaha,kategori_id,tanggal_daftar) "
                        "VALUES(?,?,?,?,?,?,?)", (body.nik, body.nama, body.no_hp, body.alamat, body.nama_usaha,
                                                  body.kategori_id, db.today(c))).lastrowid
        akun = None
        if body.buat_akun:
            uname = body.nama.split()[0].lower()
            if db.row(c, "SELECT id FROM pengguna WHERE username=?", (uname,)):
                uname = f"{uname}{did}"
            c.execute("INSERT INTO pengguna(username,password_hash,nama,peran,debitur_id) VALUES(?,?,?,?,?)",
                      (uname, auth.hash_password("debitur123"), body.nama, "DEBITUR", did))
            akun = {"username": uname, "password": "debitur123"}
        db.log(c, user["username"], "DEBITUR_BARU", {"debitur_id": did, "nama": body.nama})
        kredit = ks.ajukan_kredit(c, did, body.plafon or kat["max_plafon"], body.tenor_bulan,
                                  body.pencairan_awal, user["username"])
        return {"debitur_id": did, "akun": akun, "kredit": kredit}


@app.post("/api/debitur/{did}/insiden", tags=["Debitur"])
def tambah_insiden(did: int, body: InsidenIn, user=Depends(auth.staff)):
    with db.tx() as c:
        k = db.row(c, "SELECT id, status FROM kredit WHERE debitur_id=? AND status IN ('AKTIF','PENGAWASAN')", (did,))
        if not k:
            raise ks.BisnisError("Debitur tidak memiliki kredit aktif")
        r = wl.record_incident(c, did, body.jenis, body.keterangan, k["id"], "PETUGAS")
        if k["status"] == "AKTIF":
            c.execute("UPDATE kredit SET status='PENGAWASAN' WHERE id=?", (k["id"],))
        db.log(c, user["username"], "INSIDEN_MANUAL", {"debitur_id": did, "jenis": body.jenis})
        return r


@app.post("/api/debitur/{did}/catatan", tags=["Debitur"])
def tambah_catatan(did: int, body: CatatanIn, user=Depends(auth.staff)):
    with db.tx() as c:
        c.execute("INSERT INTO catatan_komunikasi(debitur_id,petugas,isi,tanggal) VALUES(?,?,?,?)",
                  (did, user["nama"], body.isi, db.today(c)))
        return {"ok": True}


# ================================================================ kredit
@app.post("/api/kredit", tags=["Kredit"])
def ajukan_kredit(body: KreditIn, user=Depends(auth.staff)):
    with db.tx() as c:
        d = db.row(c, "SELECT k.max_plafon FROM debitur d JOIN kategori_usaha k ON k.id=d.kategori_id WHERE d.id=?",
                   (body.debitur_id,))
        if not d:
            raise HTTPException(404, "Debitur tidak ditemukan")
        return ks.ajukan_kredit(c, body.debitur_id, body.plafon or d["max_plafon"], body.tenor_bulan,
                                body.pencairan_awal, user["username"])


@app.post("/api/kredit/{kid}/pencairan", tags=["Kredit"])
def pencairan(kid: int, body: JumlahIn, user=Depends(auth.staff)):
    with db.tx() as c:
        return ks.ajukan_pencairan(c, kid, body.jumlah, user["username"])


@app.post("/api/kredit/{kid}/bayar", tags=["Kredit"])
def bayar(kid: int, body: BayarIn, user=Depends(auth.staff)):
    with db.tx() as c:
        return ks.bayar_angsuran(c, kid, user["username"], body.jumlah_angsuran)


@app.post("/api/kredit/{kid}/lunasi", tags=["Kredit"])
def lunasi(kid: int, user=Depends(auth.staff)):
    with db.tx() as c:
        return ks.lunasi(c, kid, user["username"])


@app.get("/api/pencairan", tags=["Kredit"])
def list_pencairan(status: Optional[str] = None, user=Depends(auth.staff)):
    sql = ("SELECT p.*, d.nama, d.id AS debitur_id FROM pencairan p JOIN kredit k ON k.id=p.kredit_id "
           "JOIN debitur d ON d.id=k.debitur_id")
    args = []
    if status:
        sql += " WHERE p.status LIKE ?"
        args.append(status + "%")
    with db.read() as c:
        return db.rows(c, sql + " ORDER BY p.id DESC LIMIT 200", args)


@app.post("/api/pencairan/{pid}/batal", tags=["Kredit"])
def batal_pencairan(pid: int, user=Depends(auth.staff)):
    with db.tx() as c:
        ks.batalkan_pencairan(c, pid, user["username"])
        return {"ok": True}


# ============================================================= watchlist
@app.get("/api/watchlist", tags=["LFU Watchlist"])
def watchlist(user=Depends(auth.staff)):
    with db.read() as c:
        snap = wl.snapshot(c)
        snap["log"] = db.rows(c, "SELECT w.*, d.nama FROM watchlist_log w JOIN debitur d ON d.id=w.debitur_id "
                                 "ORDER BY w.id DESC LIMIT 60")
        snap["kandidat_luar_slot"] = db.rows(
            c, "SELECT d.id, d.nama, k.status, k.hari_tunggakan, "
               "(SELECT COUNT(*) FROM insiden_risiko i WHERE i.debitur_id=d.id) AS jumlah_insiden "
               "FROM kredit k JOIN debitur d ON d.id=k.debitur_id WHERE k.status='PENGAWASAN' "
               "AND d.id NOT IN (SELECT debitur_id FROM watchlist_slot) ORDER BY jumlah_insiden DESC")
        return snap


@app.put("/api/watchlist/kapasitas", tags=["LFU Watchlist"])
def kapasitas(body: KapasitasIn, user=Depends(auth.admin)):
    with db.tx() as c:
        out = wl.resize(c, body.kapasitas)
        db.log(c, user["username"], "UBAH_KAPASITAS_LFU", {"kapasitas": body.kapasitas, "dikeluarkan": out})
        return {"dikeluarkan": out}


# ================================================== notifikasi & arsip
@app.get("/api/notifikasi", tags=["Notifikasi"])
def notifikasi(tujuan: Optional[str] = None, user=Depends(auth.staff)):
    sql = "SELECT n.*, d.nama FROM notifikasi n LEFT JOIN debitur d ON d.id=n.debitur_id WHERE tujuan!='DEBITUR'"
    args = []
    if tujuan:
        sql += " AND tujuan=?"
        args.append(tujuan)
    with db.read() as c:
        return db.rows(c, sql + " ORDER BY n.id DESC LIMIT 200", args)


@app.post("/api/notifikasi/baca-semua", tags=["Notifikasi"])
def baca_semua(user=Depends(auth.staff)):
    with db.tx() as c:
        c.execute("UPDATE notifikasi SET dibaca=1 WHERE tujuan!='DEBITUR'")
        return {"ok": True}


@app.get("/api/arsip", tags=["Arsip"])
def arsip(user=Depends(auth.staff)):
    with db.read() as c:
        return db.rows(c, "SELECT a.*, d.nama, d.nama_usaha FROM arsip_kredit a JOIN debitur d ON d.id=a.debitur_id "
                          "ORDER BY a.id DESC")


@app.get("/api/log", tags=["Arsip"])
def log_aktivitas(user=Depends(auth.staff)):
    with db.read() as c:
        return db.rows(c, "SELECT * FROM log_aktivitas ORDER BY id DESC LIMIT 200")


# ================================================================ sistem
@app.get("/api/sistem", tags=["Sistem"])
def sistem(user=Depends(auth.current_user)):
    with db.read() as c:
        return {"parameter": db.all_params(c), "invariant_ok": ks.check_invariant(c)}


@app.post("/api/sistem/maju-hari", tags=["Sistem"])
def maju(body: MajuIn, user=Depends(auth.staff)):
    with db.tx() as c:
        return rs.maju_hari(c, body.hari)


@app.put("/api/sistem/parameter", tags=["Sistem"])
def ubah_parameter(body: dict, user=Depends(auth.admin)):
    allowed = set(config.DEFAULT_PARAMS) - {"tanggal_sistem", "pagu_dana_kur", "kapasitas_slot_lfu"}
    with db.tx() as c:
        for k, v in body.items():
            if k not in allowed:
                raise ks.BisnisError(f"Parameter '{k}' tidak dapat diubah lewat endpoint ini")
            if int(v) < 0:
                raise ks.BisnisError("Nilai parameter tidak boleh negatif")
            db.set_param(c, k, int(v))
        p = db.all_params(c)
        if not (p["grace_period_hari"] < p["pra_eskalasi_hari"] < p["eskalasi_hari"]):
            raise ks.BisnisError("Harus berlaku: grace period < pra-eskalasi < eskalasi")
        db.log(c, user["username"], "UBAH_PARAMETER", body)
        return p


@app.post("/api/sistem/reset", tags=["Sistem"])
def reset(user=Depends(auth.admin)):
    from .seed import seed
    with db._lock:  # cegah timer/request lain memakai DB selama dibangun ulang
        seed()
    return {"ok": True, "pesan": "Database direset ke data demo. Silakan login ulang."}


@app.post("/api/sistem/kosongkan", tags=["Sistem"])
def kosongkan(user=Depends(auth.admin)):
    from .seed import kosongkan
    with db._lock:
        kosongkan()
    return {"ok": True, "pesan": "Semua data dihapus. Silakan login ulang."}


# ========================================================= portal debitur
@app.get("/api/saya", tags=["Portal Debitur"])
def saya(user=Depends(auth.debitur_only)):
    with db.read() as c:
        d = _detail(c, user["debitur_id"])
        d.pop("watchlist_log", None)
        d["notifikasi"] = db.rows(c, "SELECT * FROM notifikasi WHERE debitur_id=? AND tujuan='DEBITUR' "
                                     "ORDER BY id DESC LIMIT 30", (user["debitur_id"],))
        d["tanggal_sistem"] = db.today(c)
        d["slot_pengawasan"] = d.get("frekuensi_lfu") is not None
        return d


@app.post("/api/saya/pencairan", tags=["Portal Debitur"])
def saya_pencairan(body: JumlahIn, user=Depends(auth.debitur_only)):
    with db.tx() as c:
        k = db.row(c, "SELECT id FROM kredit WHERE debitur_id=? AND status IN ('MENUNGGU','AKTIF','PENGAWASAN')",
                   (user["debitur_id"],))
        if not k:
            raise ks.BisnisError("Anda tidak memiliki fasilitas kredit aktif")
        return ks.ajukan_pencairan(c, k["id"], body.jumlah, user["username"])


@app.post("/api/saya/notifikasi/baca", tags=["Portal Debitur"])
def saya_baca(user=Depends(auth.debitur_only)):
    with db.tx() as c:
        c.execute("UPDATE notifikasi SET dibaca=1 WHERE tujuan='DEBITUR' AND debitur_id=?", (user["debitur_id"],))
        return {"ok": True}


# ============================================================ frontend
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login.html")


app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
