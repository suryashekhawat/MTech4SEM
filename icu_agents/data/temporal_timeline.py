"""Build hourly ICU timelines for dashboard scrubbing and point-in-time narratives."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from agents.risk_agent import RiskAgent
from config import MAX_ICU_HOURS
from data.eicu_loader import DEFAULT_LABS, load_temporal_events
from models.patient_state import PatientState


def _vitals_hour(vital: Dict[str, Any], index: int) -> int:
    ts = vital.get("timestamp", vital.get("hour", index))
    if isinstance(ts, str):
        return index
    return int(ts)


def _normalize_vitals(vitals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, row in enumerate(vitals):
        hour = _vitals_hour(row, index)
        normalized.append({**row, "hour": hour, "timestamp": hour})
    normalized.sort(key=lambda row: row["hour"])
    return normalized


def _labs_at_hour(lab_events: List[Dict[str, Any]], hour: int, baseline: Dict[str, float]) -> Dict[str, float]:
    labs = dict(baseline)
    for event in lab_events:
        if event["hour"] <= hour:
            labs[event["analyte"]] = event["value"]
    return labs


def _respiratory_at_hour(
    resp_events: List[Dict[str, Any]],
    hour: int,
    baseline: Dict[str, Any],
) -> Dict[str, Any]:
    snapshot = {
        "mechanical_ventilation": bool(baseline.get("mechanical_ventilation")),
        "fio2": int(baseline.get("fio2", 21)),
        "peep": int(baseline.get("peep", 5)),
        "source": baseline.get("source", "timeline"),
    }
    for event in resp_events:
        if event["hour"] > hour:
            break
        label = str(event.get("label", "")).lower()
        value = float(event.get("value", 0))
        if "fio2" in label:
            snapshot["fio2"] = int(min(100, value))
            snapshot["mechanical_ventilation"] = value > 21
        elif "peep" in label:
            snapshot["peep"] = int(value)
    return snapshot


def _note_at_hour(note_events: List[Dict[str, Any]], hour: int, baseline: Dict[str, Any]) -> Dict[str, Any]:
    latest = baseline
    for event in note_events:
        if event["hour"] <= hour:
            latest = {
                "report": f"{event.get('note_type', 'note')}: {event.get('text', '')[:500]}",
                "source": "eicu_note",
            }
    return latest


def _severity_label(vitals_row: Dict[str, Any]) -> str:
    spo2 = vitals_row.get("spo2", 100)
    heart_rate = vitals_row.get("heart_rate", 80)
    if spo2 < 85 or heart_rate > 125:
        return "critical"
    if spo2 < 90 or heart_rate > 115:
        return "worsening"
    return "stable"


def build_timeline(
    patient: PatientState,
    source: str = "eicu",
    stay_id: Optional[int] = None,
) -> Dict[str, Any]:
    vitals = _normalize_vitals(patient.vitals)
    if not vitals:
        return {
            "hours": [0],
            "vitals": [],
            "events": [],
            "lab_events": [],
            "note_events": [],
            "resp_events": [],
            "baseline_labs": dict(patient.labs or DEFAULT_LABS),
        }

    max_hour = min(MAX_ICU_HOURS, max(row["hour"] for row in vitals))
    hours = list(range(0, max_hour + 1))

    lab_events: List[Dict[str, Any]] = []
    note_events: List[Dict[str, Any]] = []
    resp_events: List[Dict[str, Any]] = []

    if source == "eicu" and stay_id is not None:
        all_events = load_temporal_events(int(stay_id))
        lab_events = [event for event in all_events if event["category"] == "lab"]
        note_events = [event for event in all_events if event["category"] == "note"]
        resp_events = [event for event in all_events if event["category"] == "respiratory"]

    baseline_labs = dict(patient.labs or DEFAULT_LABS)
    vitals_by_hour = {row["hour"]: row for row in vitals}

    events: List[Dict[str, Any]] = [
        {
            "hour": vitals[0]["hour"],
            "category": "admission",
            "summary": f"ICU stay begins — {patient.diagnosis[:120]}",
        }
    ]

    for hour in hours:
        if hour in vitals_by_hour:
            row = vitals_by_hour[hour]
            events.append(
                {
                    "hour": hour,
                    "category": "vitals",
                    "summary": (
                        f"Vitals @ hour {hour}: HR {row['heart_rate']} bpm, "
                        f"SpO₂ {row['spo2']}%, RR {row.get('resp_rate', '—')}/min"
                    ),
                    "severity": _severity_label(row),
                }
            )

    events.extend(lab_events)
    events.extend(note_events)
    events.extend(resp_events)
    events.sort(key=lambda event: (event["hour"], event["category"]))

    return {
        "hours": hours,
        "vitals": vitals,
        "events": events,
        "lab_events": lab_events,
        "note_events": note_events,
        "resp_events": resp_events,
        "baseline_labs": baseline_labs,
    }


def snapshot_at_hour(
    patient: PatientState,
    timeline: Dict[str, Any],
    hour: int,
) -> Dict[str, Any]:
    vitals = timeline["vitals"]
    vitals_up_to_hour = [row for row in vitals if row["hour"] <= hour]
    if not vitals_up_to_hour:
        vitals_up_to_hour = vitals[:1]

    current_vitals = vitals_up_to_hour[-1]
    labs = _labs_at_hour(timeline["lab_events"], hour, timeline["baseline_labs"])
    respiratory = _respiratory_at_hour(timeline["resp_events"], hour, patient.respiratory or {})
    radiology = _note_at_hour(timeline["note_events"], hour, patient.radiology or {})
    risk_scores = RiskAgent().calculate(vitals_up_to_hour, labs)
    events_up_to_hour = [event for event in timeline["events"] if event["hour"] <= hour]

    return {
        "hour": hour,
        "vitals_row": current_vitals,
        "vitals_history": vitals_up_to_hour,
        "labs": labs,
        "respiratory": respiratory,
        "radiology": radiology,
        "risk_scores": risk_scores,
        "events": events_up_to_hour,
        "severity": _severity_label(current_vitals),
        "patient": patient,
    }


def patient_view_at_hour(patient: PatientState, snapshot: Dict[str, Any]) -> PatientState:
    view = deepcopy(patient)
    view.vitals = snapshot["vitals_history"]
    view.labs = snapshot["labs"]
    view.respiratory = snapshot["respiratory"]
    view.radiology = snapshot["radiology"]
    view.risk_scores = snapshot["risk_scores"]
    return view
