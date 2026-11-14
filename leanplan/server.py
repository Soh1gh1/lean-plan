"""Loopback-only HTTP interface with same-origin mutation checks."""
from __future__ import annotations

import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import urlsplit, parse_qs

from .domain import ValidationError


def create_server(store, static_dir: Path, port=0):
    token = secrets.token_urlsafe(32)
    static_dir = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.debug(fmt, *args)

        def respond(self, body, status=200, mime="application/json; charset=utf-8", attachment=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Permissions-Policy", "fullscreen=()")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                pass

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                return self.respond({"error": "Invalid host"}, 403)
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    return self.respond({**store.state(), "token": token})
                if path.startswith("/api/archives/"):
                    return self.respond(store.archive(path.rsplit("/", 1)[-1]))
                if path == "/api/export/json":
                    return self.respond(store.export(), attachment="leanplan-backup.json")
                if path == "/api/export/csv":
                    stream = io.StringIO(newline="")
                    writer = csv.writer(stream, delimiter=";")
                    keys = ("date", "weight", "protein", "fat", "carbs", "calories", "training_minutes", "steps", "steps_kcal", "bmr", "training_kcal", "tef", "tdee", "deficit", "entered_late", "first_recorded_on", "note")
                    writer.writerow(("Date", "Weight, kg", "Protein, g", "Fat, g", "Carbs, g", "Calculated calories, kcal", "Training, minutes", "Steps", "Walking, kcal", "BMR", "Training, kcal", "TEF", "Expenditure, kcal", "Deficit, kcal", "Late entry", "First recorded on", "Note"))
                    archive_id = parse_qs(urlsplit(self.path).query).get("archive", [None])[0]
                    source = store.archive(archive_id) if archive_id else store.state()
                    for row in source["entries"]:
                        values = [row.get(key, "") for key in keys]
                        if isinstance(values[-1], str) and values[-1].lstrip().startswith(("=", "+", "-", "@")):
                            values[-1] = "'" + values[-1]
                        writer.writerow(values)
                    return self.respond(stream.getvalue().encode("utf-8-sig"), mime="text/csv; charset=utf-8", attachment="leanplan-history.csv")
                routes = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/icon.svg": "icon.svg"}
                if path not in routes:
                    return self.respond({"error": "Not found"}, 404)
                file = static_dir / routes[path]
                mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                return self.respond(file.read_bytes(), mime=mime + "; charset=utf-8")
            except ValidationError as error:
                self.respond({"error": str(error)}, 404)
            except Exception:
                logging.exception("GET failed")
                self.respond({"error": "Could not read your data. Please try again."}, 500)

        def do_POST(self):
            if not self.valid_host() or not secrets.compare_digest(self.headers.get("X-Leanplan-Token", ""), token):
                return self.respond({"error": "Refresh the app and try again."}, 403)
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get("Origin") not in (None, expected_origin):
                return self.respond({"error": "Invalid origin"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 10 * 1024 * 1024:
                    raise ValidationError("Invalid request size (maximum 10 MB).")
                body = json.loads(self.rfile.read(length))
                path = urlsplit(self.path).path
                if path == "/api/entry":
                    store.save_entry(body)
                elif path == "/api/settings":
                    store.save_settings(body)
                elif path == "/api/onboard":
                    store.onboard(body)
                elif path == "/api/period/archive":
                    store.archive_period(body)
                elif path == "/api/delete":
                    if not isinstance(body, dict):
                        raise ValidationError("Invalid request.")
                    store.delete_entry(body.get("date"))
                elif path == "/api/history/clear":
                    if not isinstance(body, dict) or body.get("confirmation") != "CLEAR":
                        raise ValidationError("Confirm clearing your entire history.")
                    store.clear_history()
                else:
                    return self.respond({"error": "Not found"}, 404)
                return self.respond({**store.state(), "token": token})
            except (ValidationError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
                self.respond({"error": str(error)}, 400)
            except Exception:
                logging.exception("POST failed")
                self.respond({"error": "Could not save. Your data is safe; please try again."}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
