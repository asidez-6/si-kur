# CLAUDE.md

SI-KUR is a university Operating Systems course project (PjBL): a KUR (Indonesian micro-credit) loan management prototype that maps OS concepts onto lending. FastAPI + SQLite backend, static vanilla-JS frontend, no build step.

All code, identifiers, comments, UI text and error messages are in **Indonesian**. Keep new code in Indonesian to match (`debitur`, `kredit`, `pencairan`, `angsuran`, `tunggakan`, ...).

## Commands

```bash
pip install -r requirements.txt
python run.py                 # serve on http://127.0.0.1:8000 (API docs at /docs)
python run.py --reset         # rebuild data/sikur.db from seed, then serve
python -m app.seed            # rebuild the demo DB only, printing the simulated history

python -m pytest tests -v                       # full suite (45 tests)
python -m pytest tests/test_bankers.py -v       # one file
python -m pytest tests -k X03 -v                # one test by ID
```

- No linter, formatter or type checker is configured.
- `uvicorn` runs with `reload=False`; restart the server after backend edits. Frontend files are served straight from `frontend/`, so a browser refresh is enough.
- `tests/test_stress.py` **rewrites `docs/hasil_stress_test.json`** on every run (module-scoped autouse fixture). That file is a deliverable for the course report; expect it to show up as modified.
- Demo logins: `admin/admin123`, `petugas/petugas123`, debtors (`siti`, `bambang`, `indah`, ...) with `debitur123`.
- `SIKUR_DB` env var overrides the database path (default `data/sikur.db`).

## OS concept mapping

This mapping is the point of the project; it drives naming and design throughout.

| OS concept | In SI-KUR | Code |
|---|---|---|
| Resource allocation (Banker's Algorithm) | Every disbursement is safe-state checked against the KUR fund | `app/algorithms/bankers.py` |
| Process / Available / Max / Allocation / Need | Loan (`kredit` row) / `dana_kur.available` / `plafon_max` / `allocation` / `plafon_max - allocation` | `kredit_service.banker_state` |
| Memory management (LFU page replacement) | Limited "intensive supervision" slots; risk incidents are page references | `app/algorithms/lfu.py` |
| Storage management | SQLite ledger + never-deleted archive | `app/schema.sql` |
| Deadlock handling | Grace period, escalation/preemption to NPL, safe-state recovery | `app/services/risk_service.py` |

## Architecture

```
app/algorithms/   pure algorithms, no DB or FastAPI imports
app/services/     business logic; every function takes an open connection `c`
app/main.py       all routes + Pydantic request models; opens the transaction, calls services
app/database.py   single global SQLite connection, tx()/read() helpers, params, log, notify
app/seed.py       init_db() + demo data
frontend/         login.html, petugas.html (staff/admin SPA), debitur.html (debtor portal)
```

**Layering.** Routes in `main.py` do `with db.tx() as c:` (writes) or `with db.read() as c:` (reads) and pass `c` into service functions. Services never open their own transaction, so they compose inside one atomic unit. Follow this when adding endpoints.

**Database access.** There is one process-wide `sqlite3` connection guarded by a `threading.RLock` (`database._lock`). `tx()` takes the lock, runs `BEGIN IMMEDIATE`, and commits or rolls back. This lock is the mutual exclusion that makes concurrent disbursement requests safe (`test_X03`). No ORM: raw SQL through `db.row()` / `db.rows()`, which return plain dicts.

**Schema changes.** `schema.sql` is `CREATE TABLE IF NOT EXISTS` only and is re-executed on every `connect()`. There are no migrations; after changing a table, rebuild with `python run.py --reset`.

**Runtime parameters.** Business rules (grace period, escalation threshold, LFU capacity, ...) live in the `parameter` table, seeded from `config.DEFAULT_PARAMS`. Read them with `db.get_param(c, key)`, never from `config` directly. A new parameter must be added to `DEFAULT_PARAMS`: `all_params()` iterates it, and `get_param` uses the default's type to decide whether to cast to `int`.

**Virtual clock.** The system date is the `tanggal_sistem` parameter, not wall-clock time. Always use `db.today(c)` for business dates. Time moves only through `risk_service.maju_hari()` (the `/api/sistem/maju-hari` endpoint, or the background `_timer_loop` in `main.py` when `auto_timer_aktif` is on). Each day advanced runs `daily_job`. Only session expiry and `log_aktivitas.waktu_nyata` use real time.

**Auth.** Opaque bearer tokens stored in the `sesi` table, PBKDF2 password hashes. Route guards are FastAPI dependencies from `auth.py`: `auth.current_user`, `auth.staff` (ADMIN + PETUGAS), `auth.admin`, `auth.debitur_only`. Debtor endpoints live under `/api/saya` and derive the debtor from the session, never from a path parameter.

**Errors.** Raise `kredit_service.BisnisError` for business-rule violations; a global handler turns it into HTTP 400 with `{"detail": ...}`. Use `HTTPException` only for 401/403/404.

## Domain rules worth knowing

**Fund conservation invariant.** `available + Σ allocation (active loans) + total_kerugian_npl == pagu`, checked by `kredit_service.check_invariant`. Any code that moves money must update `dana_kur` and `kredit.allocation` together. Tests assert this after nearly every operation.

**Loan status lifecycle** (`kredit.status`):

```
MENUNGGU ──first disbursement──▶ AKTIF ◀──30 clean days──┐
    │                              │                      │
    │                              └─late past grace─▶ PENGAWASAN ──>90 days overdue──▶ MACET
    └─cancelled / frozen─▶ DITOLAK           all installments paid ─▶ LUNAS
```

`MENUNGGU`, `AKTIF`, `PENGAWASAN` are the "active" set (`kredit_service.ACTIVE`) that participates in the Banker's state. One debtor may hold only one active loan, and a debtor with an archived `MACET` loan can never apply again.

**Disbursement** (`_proses_pencairan`) runs `bankers.request_resources` and ends as `DISETUJUI`, `DITUNDA_DANA_KURANG`, `DITUNDA_UNSAFE`, or `DITOLAK_MELEBIHI_PLAFON`. `DITUNDA_*` requests form a FIFO queue that `proses_antrean` retries whenever funds return (payment, payoff, daily job). Code matches the queue with `status LIKE 'DITUNDA%'`. Only `MENUNGGU`/`AKTIF` loans may draw; a loan may have one pending request at a time.

**Daily job order** (`risk_service.daily_job`): auto-pay by simulated debtors → per loan: recompute days overdue, record grace-period incidents (→ `PENGAWASAN`), recurring incidents every N overdue days, pre-escalation warning, escalation to `MACET`, recovery to `AKTIF` → `pulihkan_safe_state` if anything escalated → LFU aging → retry the disbursement queue.

**Escalation** (`eskalasi`) is the preemption step: allocation is zeroed, the guarantee claim (`persen_penjaminan`, 70%) returns to `available`, the remainder becomes `total_kerugian_npl`. Because that loss shrinks total capacity, a safe state can turn unsafe; `pulihkan_safe_state` then freezes unused ceilings (`plafon_max := allocation`), `PENGAWASAN` loans first, then largest Need, until the state is safe again.

**LFU watchlist.** `LFUCache` is in-memory and pure. `watchlist_service` rehydrates it from `watchlist_slot` on every call (`load_cache`) and writes it back (`save_cache`), with the `urutan` column preserving in-bucket LRU order. Always record incidents through `watchlist_service.record_incident`, which inserts the `insiden_risiko` row and updates the cache together. A debtor re-entering the cache starts at their total historical incident count, not 1.

**Simulated debtors.** `debitur.profil_simulasi` (`DISIPLIN` / `KADANG_TELAT` / `BERMASALAH` / `NULL`) drives deterministic auto-payment in `risk_service.rencana_bayar` when `simulasi_perilaku_debitur` is on. Debtors created through the API have `NULL` and never auto-pay.

**Seeding.** `seed()` deletes the DB file and replays a real day-by-day simulation from 2026-01-05 to 2026-10-08, so demo statuses, incidents and notifications are produced by the algorithms rather than inserted by hand. Changing business logic or the hash in `rencana_bayar` changes the demo data, and can break `tests/test_api.py`, which asserts on the seeded state (e.g. all four of `AKTIF`/`PENGAWASAN`/`MACET`/`LUNAS` present).

## Tests

- `fresh_db` fixture (`tests/conftest.py`): empty temp DB, date `2026-01-01`, debtor simulation **off**. Build fixtures with `buat_debitur(c, kode, plafon, tenor, cair)`; amounts use `JT = 1_000_000`.
- `test_api.py` instead points `config.DB_PATH` at a temp file and lets the app lifespan run the full seed.
- Test names carry case IDs used in the course report: `B..` (Banker's), `L..` (LFU), `S..` (credit lifecycle), `A..` (API), `X..` (stress). Keep the ID prefix when adding tests.
- `test_bankers.py` and `test_lfu.py` test the pure algorithms, including the classic Silberschatz multi-resource example. `bankers.py` is deliberately vector-based for that reason even though SI-KUR uses a single resource (`m = 1`, wrapped as `[amount]`).

## Frontend

Plain HTML/CSS/JS, no framework or bundler. `js/common.js` provides `API` (fetch wrapper that attaches the bearer token from `localStorage` and redirects to login on 401), `fmt` formatters, status badge maps, `modal`, `toast`, and `esc`. `petugas.js` is a hash-routed SPA: add a page by registering `ROUTES.<name>` and a `TITLES` entry, plus a nav link in `petugas.html`. Views are built with template strings assigned to `innerHTML`, so pass every server-supplied value through `esc()`.

Status strings from the backend are mapped to labels and colours in `STATUS` / `PENCAIRAN_STATUS` in `common.js`; add new backend statuses there too.
