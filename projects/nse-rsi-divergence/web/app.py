"""Flask dashboard for the NSE RSI-divergence screener.

Reads the daily signal snapshot written by run_daily.py. The snapshot is
fetched from GitHub at request time (cached for SNAPSHOT_TTL seconds) so the
dashboard is current without a redeploy; if that fetch fails it falls back to
the copy baked into the image, then to the SQLite store.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

app = Flask(__name__)
app.secret_key = config.SESSION_SECRET


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("auth"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


SNAPSHOT_URL = os.environ.get(
    "SNAPSHOT_URL",
    "https://raw.githubusercontent.com/dheerkapil/nse_projects/main/"
    "projects/nse-rsi-divergence/output/daily_signals.json",
)
SNAPSHOT_TTL = int(os.environ.get("SNAPSHOT_TTL", "60"))

_cache = {"at": 0.0, "data": None}


def _fetch_remote():
    """The snapshot as published by the pipeline, or None."""
    try:
        req = urllib.request.Request(
            SNAPSHOT_URL, headers={"User-Agent": "rsi-divergence-dashboard"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"snapshot: remote fetch failed ({exc})")
        return None


def load_snapshot() -> dict:
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < SNAPSHOT_TTL:
        return _cache["data"]

    data = _fetch_remote()
    if data is None:
        # Fall back to the copy baked into the image at build time.
        snap = config.OUTPUT_DIR / "daily_signals.json"
        if snap.exists():
            try:
                data = json.loads(snap.read_text())
            except Exception:
                data = None
    if data is not None:
        _cache.update(at=now, data=data)
        return data
    # Fallback: read straight from the DB (local dev)
    try:
        from src.database import get_signals
        return {
            "signals": get_signals(active_only=True),
            "profile": config.PROFILE,
            "asof": None, "generated_at": None, "count": None,
        }
    except Exception:
        return {"signals": [], "profile": config.PROFILE,
                "asof": None, "generated_at": None, "count": 0}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == config.APP_PASSWORD:
            session["auth"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Incorrect password"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    snap = load_snapshot()
    return render_template("index.html", snap=snap, signals=snap.get("signals", []))


@app.route("/api/signals")
@login_required
def api_signals():
    return jsonify(load_snapshot())


@app.route("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
