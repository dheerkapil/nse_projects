"""Flask dashboard for the NSE RSI-divergence screener.

Reads the daily signal snapshot (output/daily_signals.json) written by
run_daily.py, and falls back to the SQLite store if the snapshot is absent.
"""
from __future__ import annotations

import json
import os
import sys
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


def load_snapshot() -> dict:
    snap = config.OUTPUT_DIR / "daily_signals.json"
    if snap.exists():
        try:
            return json.loads(snap.read_text())
        except Exception:
            pass
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
