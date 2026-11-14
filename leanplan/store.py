"""Transactional autosave, late-entry provenance and local safety backups."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from .domain import DEFAULT_SETTINGS, ValidationError, build_state, has_data, macro_energy, intake_energy, calorie_source, validate_entry, validate_settings


class Store:
    def __init__(self, data_dir: Path, today_provider=date.today):
        self.data_dir = Path(data_dir)
        self.today = today_provider
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "leanplan.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK (id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entries (
                    date TEXT PRIMARY KEY, weight REAL, calories REAL, training_minutes REAL,
                    training_met REAL, steps INTEGER, steps_kcal REAL, note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    protein REAL, fat REAL, carbs REAL,
                    calorie_override REAL,
                    entered_late INTEGER NOT NULL DEFAULT 0, first_recorded_on TEXT
                );
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS archives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                    start_date TEXT NOT NULL, end_date TEXT NOT NULL, created_at TEXT NOT NULL,
                    summary TEXT NOT NULL, snapshot TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES (1, ?)", (json.dumps(DEFAULT_SETTINGS),))
        with self.connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(entries)")}
        definitions = {"protein": "REAL", "fat": "REAL", "carbs": "REAL",
                       "entered_late": "INTEGER NOT NULL DEFAULT 0", "first_recorded_on": "TEXT", "calorie_override": "REAL"}
        missing = [key for key in definitions if key not in columns]
        if missing:
            self.backup(force=True)
            with self.connect() as db:
                for column in missing:
                    db.execute(f"ALTER TABLE entries ADD COLUMN {column} {definitions[column]}")
        with self.connect() as db:
            earliest = db.execute("SELECT MIN(date) FROM entries").fetchone()[0]
            start = min(earliest, self.today().isoformat()) if earliest else self.today().isoformat()
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('journal_start', ?)", (start,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self, db=None):
        if db is not None:
            saved = json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])
            return validate_settings({}, saved)
        with self.connect() as connection:
            return self.settings(connection)

    def entries(self, db=None):
        if db is not None:
            return [dict(row) for row in db.execute("SELECT * FROM entries ORDER BY date")]
        with self.connect() as connection:
            return self.entries(connection)

    def state(self):
        with self.connect() as db:
            db.execute("BEGIN")
            baseline = self.baseline(db)
            return {**build_state(self.entries(db), self.settings(db), self.today(), baseline=baseline),
                    "baseline": baseline,
                    "archives": self.archives(db),
                    "journal_start": db.execute("SELECT value FROM metadata WHERE key='journal_start'").fetchone()[0]}

    @staticmethod
    def baseline(db):
        row = db.execute("SELECT value FROM metadata WHERE key='baseline'").fetchone()
        return json.loads(row[0]) if row else None

    def archives(self, db):
        return [{**dict(row), "summary": json.loads(row["summary"])} for row in
                db.execute("SELECT id,name,start_date,end_date,created_at,summary FROM archives ORDER BY id DESC")]

    def archive(self, archive_id):
        try:
            archive_id = int(archive_id)
        except (ValueError, TypeError):
            raise ValidationError("This archive was not found.") from None
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM archives WHERE id=?", (archive_id,)).fetchone()
        if not row:
            raise ValidationError("This archive was not found.")
        return json.loads(row[0])

    def archive_period(self, payload):
        if not isinstance(payload, dict):
            raise ValidationError("Invalid archive request.")
        name = payload.get("name", "")
        if not isinstance(name, str) or len(name) > 60 or not name.strip():
            raise ValidationError("Name this period (up to 60 characters).")
        boundary = self.today().isoformat()
        self.backup(force=True)
        with self.connect() as db:
            # Acquire the write lock before reading so the snapshot and reset
            # cannot straddle a concurrent autosave.
            db.execute("BEGIN IMMEDIATE")
            rows = [row for row in self.entries(db) if row["date"] < boundary]
            if not any(has_data(row) for row in rows):
                raise ValidationError("There are no completed days to archive yet.")
            start = db.execute("SELECT value FROM metadata WHERE key='journal_start'").fetchone()[0]
            end = (self.today() - timedelta(days=1)).isoformat()
            baseline = self.baseline(db)
            snapshot = {**build_state(rows, self.settings(db), date.fromisoformat(end), baseline=baseline),
                        "journal_start": start, "baseline": baseline,
                        "name": name.strip(), "start_date": start, "end_date": end, "read_only": True}
            created = datetime.now().isoformat(timespec="seconds")
            cursor = db.execute("INSERT INTO archives(name,start_date,end_date,created_at,summary,snapshot) VALUES(?,?,?,?,?,?)",
                                (name.strip(), start, end, created, json.dumps(snapshot["summary"]), json.dumps(snapshot)))
            snapshot["id"] = cursor.lastrowid
            db.execute("UPDATE archives SET snapshot=? WHERE id=?", (json.dumps(snapshot), cursor.lastrowid))
            db.execute("DELETE FROM entries WHERE date<?", (boundary,))
            db.execute("UPDATE metadata SET value=? WHERE key='journal_start'", (boundary,))
            weight = snapshot["summary"]["latest_weight"]
            if weight is not None:
                carried = {"weight": weight, "date": snapshot["summary"]["latest_weight_date"]}
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('baseline', ?)", (json.dumps(carried),))
            return cursor.lastrowid

    def backup(self, force=False):
        folder = self.data_dir / "backups"
        folder.mkdir(exist_ok=True)
        suffix = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f") if force else self.today().isoformat()
        destination = folder / f"leanplan-{suffix}.sqlite3"
        if not destination.exists():
            with self.connect() as db:
                target = sqlite3.connect(destination)
                try:
                    db.backup(target)
                finally:
                    target.close()
        return destination

    @staticmethod
    def _write_entry(db, entry):
        now = datetime.now().isoformat(timespec="seconds")
        columns = ("date", "weight", "calories", "training_minutes", "training_met", "steps", "steps_kcal", "note", "protein", "fat", "carbs", "entered_late", "first_recorded_on", "calorie_override")
        entry = {"entered_late": 0, "first_recorded_on": entry["date"], **entry}
        values = [entry[key] for key in columns] + [now, now]
        db.execute("""
            INSERT INTO entries (date,weight,calories,training_minutes,training_met,steps,steps_kcal,note,protein,fat,carbs,entered_late,first_recorded_on,calorie_override,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET
            weight=excluded.weight,calories=excluded.calories,training_minutes=excluded.training_minutes,
            training_met=excluded.training_met,steps=excluded.steps,steps_kcal=excluded.steps_kcal,
            note=excluded.note,protein=excluded.protein,fat=excluded.fat,carbs=excluded.carbs,
            calorie_override=excluded.calorie_override,
            entered_late=excluded.entered_late,first_recorded_on=excluded.first_recorded_on,updated_at=excluded.updated_at
        """, values)

    def save_entry(self, payload):
        if not isinstance(payload, dict):
            raise ValidationError("Invalid journal entry.")
        if payload.get("calories") not in (None, ""):
            raise ValidationError("Use calorie_override for manual calories.")
        from .domain import validate_date
        entry_date = validate_date(payload.get("date"), self.today())
        self.backup()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            start = db.execute("SELECT value FROM metadata WHERE key='journal_start'").fetchone()[0]
            if entry_date < start and db.execute("SELECT 1 FROM archives LIMIT 1").fetchone():
                raise ValidationError("This date belongs to a closed period. Archives are read-only.")
            existing = db.execute("SELECT * FROM entries WHERE date=?", (entry_date,)).fetchone()
            editable = ("weight", "protein", "fat", "carbs", "calorie_override", "training_minutes", "training_met", "steps", "steps_kcal", "note")
            merged = {key: existing[key] for key in editable} if existing else {}
            merged.update({key: payload[key] for key in editable if key in payload})
            entry = validate_entry({"date": entry_date, **merged}, self.today())
            if entry["training_met"] is None:
                entry["training_met"] = self.settings(db)["training_met"]
            entry["entered_late"] = int(bool(existing and existing["entered_late"]) or entry_date < self.today().isoformat())
            entry["first_recorded_on"] = (existing["first_recorded_on"] if existing else None) or self.today().isoformat()
            self._write_entry(db, entry)
            db.execute("UPDATE metadata SET value=MIN(value, ?) WHERE key='journal_start'", (entry_date,))

    def save_settings(self, payload):
        self.backup()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            settings = validate_settings(payload, self.settings(db))
            db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(settings, ensure_ascii=False),))
            if "training_met" in payload:
                db.execute("UPDATE entries SET training_met=?,updated_at=? WHERE date=?",
                           (settings["training_met"], datetime.now().isoformat(timespec="seconds"), self.today().isoformat()))

    def onboard(self, payload):
        if not isinstance(payload, dict):
            raise ValidationError("Invalid profile data.")
        if not isinstance(payload.get("settings", {}), dict):
            raise ValidationError("Invalid profile settings.")
        weight = payload.get("weight")
        entry = validate_entry({"date": self.today().isoformat(), "weight": weight}, self.today()) if weight not in (None, "") else None
        self.backup()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            settings = validate_settings({**payload.get("settings", {}), "onboarding_done": True}, self.settings(db))
            db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(settings, ensure_ascii=False),))
            if entry:
                existing = db.execute("SELECT * FROM entries WHERE date=?", (entry["date"],)).fetchone()
                if existing:
                    entry = {**dict(existing), "weight": entry["weight"]}
                self._write_entry(db, entry)

    def delete_entry(self, entry_date):
        from .domain import validate_date
        validate_date(entry_date, self.today())
        self.backup(force=True)
        with self.connect() as db:
            result = db.execute("DELETE FROM entries WHERE date=?", (entry_date,))
        if not result.rowcount:
            raise ValidationError("This journal entry was not found.")

    def clear_history(self):
        self.backup(force=True)
        with self.connect() as db:
            db.execute("DELETE FROM entries")
            db.execute("DELETE FROM archives")
            db.execute("DELETE FROM metadata WHERE key='baseline'")
            db.execute("UPDATE metadata SET value=? WHERE key='journal_start'", (self.today().isoformat(),))

    def export(self):
        with self.connect() as db:
            db.execute("BEGIN")
            return {"format": "leanplan", "version": 4,
                    "exported_at": datetime.now().isoformat(timespec="seconds"),
                    "settings": self.settings(db), "entries": [{**row, "calories": intake_energy(row),
                        "calculated_calories": macro_energy(row), "calories_source": calorie_source(row)} for row in self.entries(db)],
                    "journal_start": db.execute("SELECT value FROM metadata WHERE key='journal_start'").fetchone()[0],
                    "baseline": self.baseline(db),
                    "archives": [json.loads(row[0]) for row in db.execute("SELECT snapshot FROM archives ORDER BY id")]}
