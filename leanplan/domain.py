"""The spreadsheet's model, evaluated separately for every recorded date.

There are no food, macro or calorie recommendations in this module.
Missing measurements remain missing; they are never filled with zero.
"""
from __future__ import annotations

from datetime import date, timedelta
import math
from statistics import mean


DEFAULT_SETTINGS = {
    "name": "", "age": None, "height": None, "sex": None,
    "goal_weight": None, "training_met": 2.25,
    "onboarding_done": False,
}


class ValidationError(ValueError):
    pass


def number(value, label, low, high, *, integer=False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{label}: enter a number.")
    try:
        result = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        raise ValidationError(f"{label}: enter a number.") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValidationError(f"{label}: enter a value between {low} and {high}.")
    if integer and result != int(result):
        raise ValidationError(f"{label}: enter a whole number.")
    return int(result) if integer else result


def validate_date(value: str, today: date | None = None) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValidationError("Enter a valid date.") from None
    if parsed.isoformat() != value or parsed < date(1900, 1, 1):
        raise ValidationError("Enter a valid date.")
    if parsed > (today or date.today()):
        raise ValidationError("Future days cannot have actual records yet.")
    return value


def validate_entry(payload: dict, today=None, *, historical=False) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Invalid journal entry.")
    result = {"date": validate_date(payload.get("date"), today)}
    if payload.get("calories") not in (None, ""):
        raise ValidationError("Use calorie_override for manual calories.")
    fields = {
        "weight": ("Weight", 20, 500, False),
        "protein": ("Protein", 0, 1000, False),
        "fat": ("Fat", 0, 1000, False),
        "carbs": ("Carbohydrates", 0, 2000, False),
        "calorie_override": ("Calories", 0, 50000, False),
        "training_minutes": ("Training minutes", 0, 1440, False),
        "training_met": ("MET", 1, 25, False),
        "steps": ("Steps", 0, 200000, True),
        "steps_kcal": ("Walking energy", 0, 20000, False),
    }
    for key, (label, low, high, integer) in fields.items():
        result[key] = number(payload.get(key), label, low, high, integer=integer)
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValidationError("Notes can contain up to 2,000 characters.")
    result["note"] = note.strip()
    result["calories"] = intake_energy(result)
    return result


def validate_settings(payload: dict, current=None) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Invalid settings format.")
    result = {key: (current or {}).get(key, default) for key, default in DEFAULT_SETTINGS.items()}
    fields = {
        "age": ("Age", 18, 120, True), "height": ("Height", 50, 250, False),
        "goal_weight": ("Goal weight", 20, 500, False),
        "training_met": ("MET", 1, 25, False),
    }
    for key, (label, low, high, integer) in fields.items():
        if key in payload:
            result[key] = number(payload[key], label, low, high, integer=integer)
    if result["training_met"] is None:
        result["training_met"] = 2.25
    if "name" in payload:
        if not isinstance(payload["name"], str) or len(payload["name"]) > 60:
            raise ValidationError("Your name can contain up to 60 characters.")
        result["name"] = payload["name"].strip()
    for key, allowed in {"sex": (None, "male", "female")}.items():
        if key in payload:
            if payload[key] not in allowed:
                raise ValidationError("Invalid calculation mode.")
            result[key] = payload[key]
    if "onboarding_done" in payload:
        if not isinstance(payload["onboarding_done"], bool):
            raise ValidationError("Invalid setup status.")
        result["onboarding_done"] = payload["onboarding_done"]
    return result


def macro_energy(entry: dict):
    if all(entry.get(key) is None for key in ("protein", "fat", "carbs")):
        return None
    return rounded(sum(entry[key] * factor for key, factor in
                       (("protein", 4), ("fat", 9), ("carbs", 4)) if entry.get(key) is not None))


def macro_tef(entry: dict):
    if all(entry.get(key) is None for key in ("protein", "fat", "carbs")):
        return None
    return rounded(sum(entry[key] * factor for key, factor in
                       (("protein", 1), ("carbs", .3), ("fat", .18)) if entry.get(key) is not None))


def intake_energy(entry: dict):
    """A present manual value, including zero, takes precedence over macros."""
    override = entry.get("calorie_override")
    return rounded(override) if override is not None else macro_energy(entry)


def calorie_source(entry: dict):
    if entry.get("calorie_override") is not None:
        return "manual"
    return "macros" if macro_energy(entry) is not None else None


def calculate_day(entry: dict, settings: dict, weight: float | None) -> dict:
    """BMR + net training energy + explicitly entered walking energy + TEF.

    F (STEPS KCAL) and G (DAILY DEFICIT) were blank in the workbook.
    Step count is retained as a measurement, never silently converted to kcal.
    """
    bmr = None
    if weight is not None and settings["age"] is not None and settings["age"] >= 18 and settings["height"] is not None and settings["sex"] in ("male", "female"):
        constant = 5 if settings["sex"] == "male" else -161
        bmr = 10 * weight + 6.25 * settings["height"] - 5 * settings["age"] + constant
        if bmr <= 0:
            bmr = None
    calories = intake_energy(entry)
    tef = macro_tef(entry)
    minutes = entry.get("training_minutes")
    met = entry.get("training_met") or 2.25
    training = minutes * (met - 1) * 3.5 * weight / 200 if minutes is not None and weight is not None else (0 if minutes == 0 else None)
    walking = entry.get("steps_kcal")
    tdee = bmr + sum(value for value in (training, walking, tef) if value is not None) if bmr is not None else None
    deficit = tdee - calories if tdee is not None and calories is not None else None
    return {
        **entry, "calories": calories, "effective_weight": weight, "bmr": rounded(bmr),
        "calculated_calories": macro_energy(entry), "calories_source": calorie_source(entry),
        "bmr_formula": "mifflin_st_jeor",
        "training_kcal": rounded(training), "tef": rounded(tef),
        "tdee": rounded(tdee), "deficit": rounded(deficit),
        "training_met_used": met, "has_data": has_data(entry),
    }


def rounded(value):
    """Round half away from zero, consistently with the live JS model."""
    if value is None:
        return None
    scaled = abs(value) * 1000
    # Means and subtraction can land a few floating-point bits below a tie.
    # Keep the half-away rule stable across Python and JavaScript.
    tolerance = 4 * 2**-52 * max(1, scaled)
    result = math.floor(scaled + .5 + tolerance) / 1000
    return (-result if value < 0 else result) if result else 0


def has_data(entry: dict) -> bool:
    return any(entry.get(key) is not None for key in (
        "weight", "protein", "fat", "carbs", "calorie_override", "training_minutes", "steps", "steps_kcal"
    )) or bool(entry.get("note"))


def build_state(entries: list[dict], settings: dict, today: date | None = None, *, baseline=None) -> dict:
    today = today or date.today()
    ordered = sorted((row for row in entries if row["date"] <= today.isoformat()), key=lambda row: row["date"])
    baseline = baseline or {}
    effective_weight = baseline.get("weight")
    effective_date = baseline.get("date")
    computed = []
    for entry in ordered:
        if entry["weight"] is not None:
            effective_weight, effective_date = entry["weight"], entry["date"]
        day = calculate_day(entry, settings, effective_weight)
        day["weight_source_date"] = effective_date
        computed.append(day)
    today_entry = next((row for row in computed if row["date"] == today.isoformat()), None)
    current = today_entry or calculate_day({"date": today.isoformat()}, settings, effective_weight)
    current["weight_source_date"] = effective_date
    weights = [row for row in computed if row["weight"] is not None]
    calories = [row["calories"] for row in computed if row["calories"] is not None]
    deficits = [row["deficit"] for row in computed if row["deficit"] is not None]
    recent = [row["weight"] for row in weights if today - timedelta(days=6) <= date.fromisoformat(row["date"]) <= today]
    previous = [row["weight"] for row in weights if today - timedelta(days=13) <= date.fromisoformat(row["date"]) <= today - timedelta(days=7)]
    trend_change = mean(recent) - mean(previous) if recent and previous else None
    start = baseline.get("weight", weights[0]["weight"] if weights else None)
    latest = weights[-1]["weight"] if weights else baseline.get("weight")
    goal = settings["goal_weight"]
    progress = None
    if goal is not None and start is not None:
        if goal == start:
            progress = 100 if latest == goal else 0
        else:
            progress = max(0, min(100, 100 * (latest - start) / (goal - start)))
    dates_with_data = {row["date"] for row in computed if row["weight"] is not None or any(row.get(key) is not None for key in ("protein", "fat", "carbs", "calorie_override"))}
    cursor = today if today.isoformat() in dates_with_data else today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in dates_with_data:
        streak += 1
        cursor -= timedelta(days=1)
    for row in computed:
        row_date = date.fromisoformat(row["date"])
        sample = [w["weight"] for w in weights if row_date - timedelta(days=6) <= date.fromisoformat(w["date"]) <= row_date]
        row["weight_average"] = rounded(mean(sample)) if sample else None
        row["weight_average_samples"] = len(sample)
    return {
        "today": today.isoformat(), "settings": settings, "entries": computed,
        "today_stats": current,
        "summary": {
            "entry_count": sum(row["has_data"] for row in computed), "weight_count": len(weights), "calorie_count": len(calories),
            "latest_weight": latest, "latest_weight_date": weights[-1]["date"] if weights else baseline.get("date"),
            "start_weight": start, "start_date": baseline.get("date", weights[0]["date"] if weights else None),
            "weight_change": rounded(latest - start) if weights and (len(weights) >= 2 or baseline.get("weight") is not None) else None,
            "average_calories": rounded(mean(calories)) if calories else None,
            "total_deficit": rounded(sum(deficits)) if deficits else None,
            "deficit_days": len(deficits), "streak": streak,
            "recent_average": rounded(mean(recent)) if recent else None,
            "previous_average": rounded(mean(previous)) if previous else None,
            "recent_samples": len(recent), "previous_samples": len(previous),
            "trend_change": rounded(trend_change), "goal_progress": rounded(progress),
        },
    }
