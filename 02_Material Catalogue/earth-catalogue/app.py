#!/usr/bin/env python3
"""
Earth Materials Catalogue - local server.

What it does
  * serves the web UI (static/index.html)
  * holds the Gemini API key (env var or .env) so the browser never sees it
  * stores the catalogue, the source PDFs and the Grasshopper export on disk
  * serves the Grasshopper export at /export.json

Run:   python app.py        then open http://127.0.0.1:8000
"""
import base64
import hashlib
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

BASE = Path(__file__).resolve().parent


# ----------------------------------------------------------------------------
# config
# ----------------------------------------------------------------------------
def load_dotenv(path: Path) -> None:
    """Tiny .env reader. Real environment variables win over the file."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


load_dotenv(BASE / ".env")

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
DATA = Path(os.environ.get("CATALOGUE_DATA", BASE / "data")).resolve()
MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELS", "gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite").split(",") if m.strip()]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Optional cloud copy of the Grasshopper export (Supabase Storage)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()   # secret: server side only
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "catalogue").strip()

# Gemini limits the whole inline request to ~20 MB and base64 adds a third.
MAX_INLINE_PDF = 14 * 1024 * 1024
MAX_PDF_UPLOAD = 60 * 1024 * 1024
BACKUP_EVERY_SECONDS = 600
BACKUP_KEEP = 40

CATALOGUE_FILE = DATA / "catalogue.json"
EXPORT_ALL = DATA / "exports" / "earth_materials_catalogue.json"
EXPORT_VERIFIED = DATA / "exports" / "earth_materials_catalogue_verified.json"
PDF_DIR = DATA / "pdfs"
BACKUP_DIR = DATA / "backups"
for d in (PDF_DIR, BACKUP_DIR, EXPORT_ALL.parent):
    d.mkdir(parents=True, exist_ok=True)

PROMPT = (BASE / "prompt.txt").read_text(encoding="utf-8")
CHECK_PROMPT = (BASE / "check_prompt.txt").read_text(encoding="utf-8")

# Inbox: a folder you drop PDFs into. The app lists new ones, gives each a quick check, and extracts on request.
INBOX_DEFAULT = DATA / "inbox"
INBOX_DIR = Path(os.environ.get("INBOX_DIR", INBOX_DEFAULT)).expanduser().resolve()
INBOX_FILE = DATA / "inbox.json"
if INBOX_DIR == INBOX_DEFAULT.resolve():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)   # never create a folder you named yourself (a typo would hide)
PDF_ID = re.compile(r"^[0-9a-f]{64}$")
lock = threading.Lock()

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 90 * 1024 * 1024


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# ----------------------------------------------------------------------------
# guard rails: this server is localhost-only, and must not be drivable by other
# web pages open in the same browser (DNS rebinding / cross-site requests)
# ----------------------------------------------------------------------------
@app.before_request
def guard():
    allowed_hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"}
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        allowed_hosts.add(request.host)  # you chose to expose it; Host check is then moot
    if request.host not in allowed_hosts:
        return err("Bad Host header", 403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # a custom header forces a CORS preflight, which this server never approves
        if request.headers.get("X-Catalogue-Client") != "1":
            return err("Missing client header", 403)
        origin = request.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] not in allowed_hosts:
            return err("Cross-origin request refused", 403)


@app.after_request
def headers(resp):
    # the page may only talk to this server, so injected script cannot send data elsewhere via fetch()
    resp.headers["Content-Security-Policy"] = "connect-src 'self'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ----------------------------------------------------------------------------
# pages
# ----------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(BASE / "static", "index.html")


@app.get("/api/status")
def status():
    return jsonify({
        "key_configured": bool(api_key()),
        "models": MODELS,
        "max_inline_pdf_bytes": MAX_INLINE_PDF,
        "data_dir": str(DATA),
        "cloud_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "cloud_urls": cloud_urls() if SUPABASE_URL else None,
        "inbox_dir": str(INBOX_DIR),
    })


# ----------------------------------------------------------------------------
# catalogue storage (whole-catalogue replace, atomic write, rolling backups)
# ----------------------------------------------------------------------------
def atomic_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_records():
    if not CATALOGUE_FILE.exists():
        return []
    try:
        data = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
        return data.get("records", []) if isinstance(data, dict) else []
    except Exception:
        return None  # unreadable file: caller must not overwrite blindly


def backup_if_needed(old_count: int, new_count: int, force: bool = False) -> None:
    if not CATALOGUE_FILE.exists():
        return
    backups = sorted(BACKUP_DIR.glob("catalogue_*.json"))
    recent = backups and (time.time() - backups[-1].stat().st_mtime) < BACKUP_EVERY_SECONDS
    shrinking = new_count < old_count  # deletions always get a backup first
    if recent and not shrinking and not force:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(CATALOGUE_FILE, BACKUP_DIR / f"catalogue_{stamp}.json")
    for old in sorted(BACKUP_DIR.glob("catalogue_*.json"))[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)


@app.get("/api/catalogue")
def get_catalogue():
    with lock:
        recs = read_records()
    if recs is None:
        return err("catalogue.json exists but cannot be read. Restore one from data/backups/.", 500)
    return jsonify({"records": recs})


@app.put("/api/catalogue")
def put_catalogue():
    body = request.get_json(silent=True) or {}
    records = body.get("records")
    if not isinstance(records, list):
        return err("records must be a list")
    with lock:
        old = read_records()
        if old is None:
            return err("Existing catalogue.json is unreadable; refusing to overwrite. Check data/backups/.", 500)
        backup_if_needed(len(old), len(records), force=body.get("force_backup") is True)
        atomic_write(CATALOGUE_FILE, {"schema": "earth_catalogue_store", "version": 1,
                                      "saved_at": datetime.now().isoformat(timespec="seconds"),
                                      "records": records})
        if isinstance(body.get("export_all"), dict):
            atomic_write(EXPORT_ALL, body["export_all"])
        if isinstance(body.get("export_verified"), dict):
            atomic_write(EXPORT_VERIFIED, body["export_verified"])
    return jsonify({"ok": True, "count": len(records)})


@app.get("/export.json")
def export_json():
    """For Grasshopper:  /export.json  or  /export.json?verified_only=1"""
    path = EXPORT_VERIFIED if request.args.get("verified_only") in ("1", "true", "yes") else EXPORT_ALL
    if not path.exists():
        return err("No export yet. Open the app and add or edit a record first.", 404)
    return Response(path.read_bytes(), mimetype="application/json")


@app.get("/api/soil_map")
def soil_map():
    """World soil areas with topsoil clay/silt/sand, for the reverse match ('Where can I build this?')."""
    path = DATA / "soil_map.geojson"
    if not path.exists():
        return err("No soil map yet. Run: python \"01_Soil Extraction/build_soil_map.py\"", 404)
    return send_file(path, mimetype="application/geo+json")


# ----------------------------------------------------------------------------
# cloud publish (Supabase Storage) so Grasshopper can fetch the catalogue by URL
# ----------------------------------------------------------------------------
def cloud_urls() -> dict:
    root = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}"
    return {"verified": f"{root}/{EXPORT_VERIFIED.name}", "all": f"{root}/{EXPORT_ALL.name}"}


def supabase_upload(name: str, blob: bytes) -> None:
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json",
               "x-upsert": "true", "cache-control": "max-age=0"}
    if SUPABASE_KEY.startswith("eyJ"):          # legacy JWT-style service_role key
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    try:
        r = requests.post(f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{name}",
                          headers=headers, data=blob, timeout=60)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error talking to Supabase: {type(e).__name__}") from None
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase said HTTP {r.status_code}: {r.text[:300]}")


@app.post("/api/publish")
def publish():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return err("Cloud is not configured. Add SUPABASE_URL and SUPABASE_SERVICE_KEY to .env and restart.", 400)
    sent = []
    with lock:
        for path in (EXPORT_VERIFIED, EXPORT_ALL):
            if not path.exists():
                return err("No export yet. Add or edit a record first so the export file exists.", 404)
            try:
                supabase_upload(path.name, path.read_bytes())
            except RuntimeError as e:
                return err(str(e), 502)
            sent.append(path.name)
    return jsonify({"ok": True, "uploaded": sent, "urls": cloud_urls()})


# ----------------------------------------------------------------------------
# PDF store (content-addressed, so re-uploading the same paper is free)
# ----------------------------------------------------------------------------
@app.post("/api/pdfs")
def upload_pdf():
    blob = request.get_data()
    if not blob.startswith(b"%PDF"):
        return err("That is not a PDF file.")
    if len(blob) > MAX_PDF_UPLOAD:
        return err("PDF is too large.", 413)
    pid = hashlib.sha256(blob).hexdigest()
    path = PDF_DIR / f"{pid}.pdf"
    if not path.exists():
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, path)
    return jsonify({"id": pid, "size": len(blob)})


@app.get("/api/pdfs/<pid>")
def get_pdf(pid):
    if not PDF_ID.match(pid):
        return err("Bad id", 400)
    path = PDF_DIR / f"{pid}.pdf"
    if not path.exists():
        return err("PDF not found", 404)
    return send_file(path, mimetype="application/pdf", conditional=True)


# ----------------------------------------------------------------------------
# Gemini
# ----------------------------------------------------------------------------
def gemini_call(model: str, parts: list, system: str | None, json_mode: bool) -> str:
    key = api_key()
    if not key:
        raise RuntimeError("No GEMINI_API_KEY on the server. Put it in .env or the environment, then restart.")
    body = {"contents": [{"role": "user", "parts": parts}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json", "temperature": 0}
    try:
        # key goes in a header, never in the URL, so it cannot leak through logs or history
        r = requests.post(f"{GEMINI_BASE}/{model}:generateContent",
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json=body, timeout=420)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error calling {model}: {type(e).__name__}") from None
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError(f"{model} returned HTTP {r.status_code} with a non-JSON body") from None
    if "error" in j:
        raise RuntimeError(j["error"].get("message") or f"Gemini error on {model}")
    text = "".join(p.get("text", "") for p in
                   (j.get("candidates") or [{}])[0].get("content", {}).get("parts", []))
    if not text:
        reason = (j.get("candidates") or [{}])[0].get("finishReason") or (j.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError(f"Empty response from {model}" + (f" ({reason})" if reason else ""))
    return text


def parse_model_json(s: str):
    cleaned = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", s.strip(), flags=re.I))
    parsed = json.loads(cleaned)
    return {"materials": parsed} if isinstance(parsed, list) else parsed


@app.post("/api/extract")
def extract():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    pid = body.get("pdf_id")
    images = body.get("images") or []
    wanted = body.get("model") or "cascade"
    warnings = []

    if wanted == "cascade":
        models = MODELS
    elif wanted in MODELS:
        models = [wanted]
    else:
        return err("Unknown model. Models are configured on the server (GEMINI_MODELS).")

    parts = []
    if pid:
        if not PDF_ID.match(str(pid)) or not (PDF_DIR / f"{pid}.pdf").exists():
            return err("Stored PDF not found.")
        blob = (PDF_DIR / f"{pid}.pdf").read_bytes()
        if len(blob) <= MAX_INLINE_PDF:
            parts.append({"inlineData": {"mimeType": "application/pdf", "data": base64.b64encode(blob).decode()}})
        elif not text:
            return err(f"PDF is over {MAX_INLINE_PDF // 1024 // 1024} MB and no text was given. "
                       "Re-extract it from the Paper Ingestion tab so its text is sent.")
        else:
            warnings.append(f"PDF is over {MAX_INLINE_PDF // 1024 // 1024} MB, so only its text was sent.")
    for img in images[:12]:
        mt = img.get("mimeType", "")
        if mt.startswith("image/") and img.get("data"):
            parts.append({"inlineData": {"mimeType": mt, "data": img["data"]}})
    if not (parts or text):
        return err("Nothing to extract from.")
    parts.append({"text": f"PAPER TEXT (page markers show PDF page numbers):\n{text}" if text
                  else "Extract all earth-material records from the attached document."})

    last = None
    for i, m in enumerate(models):
        try:
            result = parse_model_json(gemini_call(m, parts, PROMPT, True))
            if i > 0:
                warnings.append(f"Recovered with fallback model {m}.")
            return jsonify({"result": result, "model_used": m, "warnings": warnings})
        except json.JSONDecodeError:
            last = RuntimeError(f"{m} returned text that was not valid JSON")
        except RuntimeError as e:
            last = e
        app.logger.warning("extract failed on %s: %s", m, last)
        time.sleep(0.4)
    return err(f"All models failed. Last error: {last}", 502)


def run_models(parts: list, system: str):
    """Try the configured models in order; return (parsed JSON, model used)."""
    last = None
    for m in MODELS:
        try:
            return parse_model_json(gemini_call(m, parts, system, True)), m
        except json.JSONDecodeError:
            last = RuntimeError(f"{m} returned text that was not valid JSON")
        except RuntimeError as e:
            last = e
        app.logger.warning("call failed on %s: %s", m, last)
        time.sleep(0.4)
    raise RuntimeError(f"All models failed. Last error: {last}")


# ----------------------------------------------------------------------------
# Inbox: folder scan, quick check, import into the PDF store
# inbox.json: { sha256: {name, path (relative to INBOX_DIR), size, mtime, status, check, verdict, ...} }
#   status: new -> checked -> extracted, or skipped
# ----------------------------------------------------------------------------
def read_inbox() -> dict:
    if not INBOX_FILE.exists():
        return {}
    try:
        d = json.loads(INBOX_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_inbox() -> dict:
    """Add new PDFs to inbox.json. Files are known by content, so renaming or moving one is not 'new'."""
    inbox = read_inbox()
    by_path = {e.get("path"): k for k, e in inbox.items()}
    seen = set()
    if INBOX_DIR.is_dir():
        for p in sorted(INBOX_DIR.rglob("*")):
            if not p.is_file() or p.suffix.lower() != ".pdf":
                continue
            st, rel = p.stat(), p.relative_to(INBOX_DIR).as_posix()
            k = by_path.get(rel)
            if k and inbox[k].get("size") == st.st_size and inbox[k].get("mtime") == int(st.st_mtime):
                seen.add(k)
                continue                                   # unchanged: no need to hash again
            h = sha256_file(p)
            e = inbox.setdefault(h, {"status": "new", "found_at": datetime.now().isoformat(timespec="seconds")})
            e.update(name=p.name, path=rel, size=st.st_size, mtime=int(st.st_mtime))
            seen.add(h)
    for k, e in inbox.items():
        e["present"] = k in seen
    atomic_write(INBOX_FILE, inbox)
    return inbox


def inbox_pdf_path(pid: str, inbox: dict) -> Path:
    e = inbox.get(pid)
    if not e or not e.get("present"):
        raise FileNotFoundError("That PDF is no longer in the inbox folder. Rescan.")
    p = (INBOX_DIR / e["path"]).resolve()
    if INBOX_DIR not in p.parents:
        raise FileNotFoundError("Path outside the inbox folder.")
    return p


def import_inbox_pdf(pid: str, inbox: dict) -> Path:
    """Copy an inbox PDF into the content-addressed store (data/pdfs). Returns the stored path."""
    dest = PDF_DIR / f"{pid}.pdf"
    if dest.exists():
        return dest
    src = inbox_pdf_path(pid, inbox)
    blob = src.read_bytes()
    if hashlib.sha256(blob).hexdigest() != pid:
        raise FileNotFoundError("The file changed since the last scan. Rescan.")
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, dest)
    return dest


def verdict(c: dict):
    """recommended = measured data that meets the minimum for at least one domain (see index.html DOMAINS)."""
    r = c.get("reports") or {}
    has = lambda k, ok=("yes",): r.get(k) in ok
    rho = has("dry_density", ("yes", "specimen_mass_and_size"))
    need = {
        "mechanical": [("fc", has("compressive_strength")), ("E", has("elastic_modulus", ("yes", "curve_only"))), ("density", rho)],
        "thermal": [("conductivity", has("thermal_conductivity")), ("density", rho)],
    }
    # a paper belongs to a domain when it reports that domain's own values (density alone belongs to neither)
    touches = {"mechanical": has("compressive_strength") or has("elastic_modulus", ("yes", "curve_only")),
               "thermal": has("thermal_conductivity") or has("specific_heat", ("yes", "diffusivity_only"))}
    met = [d for d, items in need.items() if all(ok for _, ok in items)]
    measured = c.get("data_origin") in ("measured_in_this_paper", "mixed")
    notes = []
    for d, items in need.items():
        if touches[d]:
            missing = [n for n, ok in items if not ok]
            notes.append(f"{d}: " + ("complete" if not missing else "missing " + ", ".join(missing)))
    if has("soil_grading"):
        notes.append("soil grading")
    if c.get("is_earth_material_paper") is False:
        return "not_relevant", met, "not about earth building materials"
    if not measured:
        notes.insert(0, "data only cited from other studies")
    if measured and met:
        v = "recommended"
    elif any(x in ("yes", "curve_only", "specimen_mass_and_size", "diffusivity_only") for x in r.values()):
        v = "partial"
    else:
        v = "not_useful"
    return v, met, "; ".join(notes) or "no relevant data found"


def inbox_view(inbox: dict) -> list:
    old = read_records() or []
    in_cat = {(r.get("paper") or {}).get("pdf_id") for r in old}
    return [dict(e, id=k, in_catalogue=k in in_cat) for k, e in inbox.items() if e.get("present")]


@app.get("/api/inbox")
def get_inbox():
    with lock:
        inbox = scan_inbox()
    return jsonify({"dir": str(INBOX_DIR), "exists": INBOX_DIR.is_dir(), "papers": inbox_view(inbox)})


@app.post("/api/inbox/<pid>/import")
def inbox_import(pid):
    if not PDF_ID.match(pid):
        return err("Bad id")
    with lock:
        try:
            import_inbox_pdf(pid, read_inbox())
        except FileNotFoundError as e:
            return err(str(e), 404)
    return jsonify({"pdf_id": pid})


@app.post("/api/inbox/<pid>/check")
def inbox_check(pid):
    if not PDF_ID.match(pid):
        return err("Bad id")
    with lock:
        inbox = read_inbox()
        try:
            path = import_inbox_pdf(pid, inbox)
        except FileNotFoundError as e:
            return err(str(e), 404)
    blob = path.read_bytes()
    if len(blob) > MAX_INLINE_PDF:
        return err(f"PDF is over {MAX_INLINE_PDF // 1024 // 1024} MB; check it by hand and use Extract from the Paper Ingestion tab.")
    parts = [{"inlineData": {"mimeType": "application/pdf", "data": base64.b64encode(blob).decode()}},
             {"text": "Inspect the attached paper."}]
    try:
        check, model = run_models(parts, CHECK_PROMPT)
    except RuntimeError as e:
        return err(str(e), 502)
    v, met, why = verdict(check)
    with lock:
        inbox = read_inbox()
        e = inbox.get(pid)
        if e is None:
            return err("Not in the inbox any more. Rescan.", 404)
        e.update(check=check, verdict=v, domains=met, reason=why, model=model,
                 checked_at=datetime.now().isoformat(timespec="seconds"))
        if e.get("status") == "new":
            e["status"] = "checked"
        atomic_write(INBOX_FILE, inbox)
    return jsonify(dict(e, id=pid))


@app.post("/api/inbox/<pid>/status")
def inbox_status(pid):
    s = (request.get_json(silent=True) or {}).get("status")
    if not PDF_ID.match(pid) or s not in ("new", "checked", "extracted", "skipped"):
        return err("Bad id or status")
    with lock:
        inbox = read_inbox()
        if pid not in inbox:
            return err("Not in the inbox.", 404)
        inbox[pid]["status"] = s
        atomic_write(INBOX_FILE, inbox)
    return jsonify({"ok": True})


@app.post("/api/test")
def test_connection():
    last = None
    for m in MODELS:
        try:
            gemini_call(m, [{"text": "Reply with the word ok."}], None, False)
            return jsonify({"ok": True, "model": m})
        except RuntimeError as e:
            last = f"{m}: {e}"
    return jsonify({"ok": False, "error": last or "No models configured"}), 200


if __name__ == "__main__":
    print(f"\n  Earth Materials Catalogue\n  http://{HOST}:{PORT}\n  data folder : {DATA}")
    print(f"  API key     : {'loaded' if api_key() else 'MISSING (set GEMINI_API_KEY in .env)'}")
    print(f"  models      : {', '.join(MODELS)}")
    print(f"  Grasshopper : http://{HOST}:{PORT}/export.json")
    print(f"  Inbox       : {INBOX_DIR}" + ("" if INBOX_DIR.is_dir() else "   (FOLDER NOT FOUND: check INBOX_DIR in .env)"))
    print(f"  Cloud       : {'configured (' + SUPABASE_BUCKET + ')' if SUPABASE_URL and SUPABASE_KEY else 'not configured (optional)'}\n")
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print("  WARNING: bound to a non-local address. Anyone who can reach it can spend your API quota.\n")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
