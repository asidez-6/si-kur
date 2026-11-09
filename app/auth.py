"""Autentikasi sederhana berbasis token sesi (prototype)."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException

from . import config
from . import database as db


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120_000)
    return salt.hex() + "$" + dk.hex()


def verify_password(pw: str, stored: str) -> bool:
    salt_hex, dk_hex = stored.split("$")
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def login(username: str, password: str) -> dict | None:
    with db.tx() as c:
        u = db.row(c, "SELECT * FROM pengguna WHERE username=?", (username,))
        if not u or not verify_password(password, u["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        exp = (datetime.now() + timedelta(hours=config.SESSION_HOURS)).isoformat()
        c.execute("INSERT INTO sesi(token,pengguna_id,kedaluwarsa) VALUES(?,?,?)", (token, u["id"], exp))
        db.log(c, u["username"], "LOGIN")
        return {"token": token, "pengguna": _public(u)}


def logout(token: str):
    with db.tx() as c:
        c.execute("DELETE FROM sesi WHERE token=?", (token,))


def _public(u: dict) -> dict:
    return {k: u[k] for k in ("id", "username", "nama", "peran", "debitur_id")}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Belum login")
    token = authorization.split(" ", 1)[1]
    with db.read() as c:
        r = db.row(c, "SELECT p.*, s.kedaluwarsa, s.token FROM sesi s JOIN pengguna p ON p.id=s.pengguna_id "
                      "WHERE s.token=?", (token,))
    if not r or r["kedaluwarsa"] < datetime.now().isoformat():
        raise HTTPException(401, "Sesi tidak valid atau kedaluwarsa")
    u = _public(r)
    u["token"] = token
    return u


def require(*roles):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["peran"] not in roles:
            raise HTTPException(403, f"Akses khusus {', '.join(roles)}")
        return user
    return dep


staff = require("ADMIN", "PETUGAS")
admin = require("ADMIN")
debitur_only = require("DEBITUR")
