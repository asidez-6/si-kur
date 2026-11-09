"""Uji integrasi REST API + hak akses peran (TC-A01 .. TC-A09)."""
import pytest
from fastapi.testclient import TestClient

from app import config


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    config.DB_PATH = tmp_path_factory.mktemp("api") / "api.db"
    from app.main import app
    with TestClient(app) as cl:   # lifespan -> database kosong -> seed data demo
        yield cl


def tok(client, u, p):
    r = client.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_A01_login_gagal_dan_tanpa_token(client):
    assert client.post("/api/auth/login", json={"username": "petugas", "password": "salah"}).status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_A02_hak_akses_peran(client):
    deb = tok(client, "bambang", "debitur123")
    pet = tok(client, "petugas", "petugas123")
    assert client.get("/api/dashboard", headers=deb).status_code == 403
    assert client.get("/api/saya", headers=pet).status_code == 403
    assert client.put("/api/sistem/parameter", json={"grace_period_hari": 5}, headers=pet).status_code == 403


def test_A03_dashboard_safe_dan_invariant(client):
    d = client.get("/api/dashboard", headers=tok(client, "petugas", "petugas123")).json()
    assert d["safe"] is True and d["invariant_ok"] is True
    assert d["watchlist"]["terisi"] <= d["watchlist"]["kapasitas"]
    assert {"AKTIF", "PENGAWASAN", "MACET", "LUNAS"} <= set(d["status_kredit"])


def test_A04_simulasi_tidak_mengubah_data(client):
    h = tok(client, "petugas", "petugas123")
    s0 = client.get("/api/bankers/state", headers=h).json()
    k = next(p for p in s0["proses"] if p["status"] == "AKTIF" and p["need"] > 0)
    r = client.post(f"/api/bankers/simulasi/{k['kredit_id']}", json={"jumlah": 1_000_000}, headers=h).json()
    assert "status" in r
    assert client.get("/api/bankers/state", headers=h).json()["available"] == s0["available"]


def test_A05_debitur_baru_validasi_nik(client):
    h = tok(client, "petugas", "petugas123")
    bad = client.post("/api/debitur", json={"nik": "123", "nama": "Tes", "nama_usaha": "Usaha", "kategori_id": 1}, headers=h)
    assert bad.status_code == 422
    ok = client.post("/api/debitur", json={"nik": "3573999999990001", "nama": "Budi Uji", "nama_usaha": "Warung Uji",
                                           "kategori_id": 1, "tenor_bulan": 12, "pencairan_awal": 5_000_000}, headers=h)
    assert ok.status_code == 200 and ok.json()["kredit"]["status"] == "AKTIF"
    dup = client.post("/api/debitur", json={"nik": "3573999999990001", "nama": "Budi Lagi", "nama_usaha": "Warung",
                                            "kategori_id": 1}, headers=h)
    assert dup.status_code == 400


def test_A06_portal_debitur(client):
    h = tok(client, "budi", "debitur123")
    me = client.get("/api/saya", headers=h).json()
    assert me["nama"] == "Budi Uji" and me["status"] == "AKTIF"
    assert all(n["tujuan"] == "DEBITUR" for n in me["notifikasi"])
    r = client.post("/api/saya/pencairan", json={"jumlah": 99_000_000}, headers=h).json()
    assert r["status"] == "DITOLAK_MELEBIHI_PLAFON"


def test_A07_parameter_harus_konsisten(client):
    h = tok(client, "admin", "admin123")
    r = client.put("/api/sistem/parameter", json={"grace_period_hari": 100}, headers=h)
    assert r.status_code == 400
    r = client.put("/api/sistem/parameter", json={"tanggal_sistem": 1}, headers=h)
    assert r.status_code == 400


def test_A08_maju_hari_dan_frontend(client):
    h = tok(client, "petugas", "petugas123")
    r = client.post("/api/sistem/maju-hari", json={"hari": 20}, headers=h).json()
    assert r["tanggal_sistem"] == "2026-10-28"
    assert len(r["eskalasi"]) >= 1          # Indah Permata (tunggakan 75 hari) tereskalasi
    assert client.get("/api/sistem", headers=h).json()["invariant_ok"]
    for page in ("/login.html", "/petugas.html", "/debitur.html", "/js/petugas.js", "/css/style.css"):
        assert client.get(page).status_code == 200


def test_A09_hapus_semua_data(client):
    # dijalankan paling akhir: mengosongkan DB lalu mengembalikan data demo
    assert client.post("/api/sistem/kosongkan", headers=tok(client, "petugas", "petugas123")).status_code == 403
    tgl = client.get("/api/dashboard", headers=tok(client, "admin", "admin123")).json()["tanggal_sistem"]
    assert client.post("/api/sistem/kosongkan", headers=tok(client, "admin", "admin123")).status_code == 200
    assert client.post("/api/auth/login", json={"username": "bambang", "password": "debitur123"}).status_code == 401
    d = client.get("/api/dashboard", headers=tok(client, "admin", "admin123")).json()
    assert d["tanggal_sistem"] == tgl and d["status_kredit"] == {} and d["invariant_ok"]
    assert d["dana"]["available"] == d["dana"]["pagu"]
    assert client.post("/api/sistem/reset", headers=tok(client, "admin", "admin123")).status_code == 200
