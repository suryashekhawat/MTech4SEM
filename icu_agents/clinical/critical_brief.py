"""Critical Patient Brief: SBAR, trends, alerts, and recommended actions at a point in time."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.patient_state import PatientState


LOOKBACK_HOURS = 6


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vitals_at_hour(vitals: List[Dict[str, Any]], hour: int) -> Optional[Dict[str, Any]]:
    rows = [row for row in vitals if int(row.get("hour", -1)) <= hour]
    if not rows:
        return None
    return rows[-1]


def _labs_at_hour(timeline: Dict[str, Any], hour: int) -> Dict[str, float]:
    baseline = dict(timeline.get("baseline_labs", {}))
    for event in timeline.get("lab_events", []):
        if event["hour"] <= hour:
            baseline[event["analyte"]] = event["value"]
    return baseline


def _lab_value_at_hour(timeline: Dict[str, Any], analyte: str, hour: int) -> Optional[float]:
    value = None
    for event in timeline.get("lab_events", []):
        if event.get("analyte") == analyte and event["hour"] <= hour:
            value = event["value"]
    if value is not None:
        return float(value)
    return _safe_float(_labs_at_hour(timeline, hour).get(analyte))


def _last_lab_hour(timeline: Dict[str, Any], analyte: str, up_to_hour: int) -> Optional[int]:
    last_hour = None
    for event in timeline.get("lab_events", []):
        if event.get("analyte") == analyte and event["hour"] <= up_to_hour:
            last_hour = event["hour"]
    return last_hour


def _trend_direction(delta: Optional[float], higher_is_worse: bool = True) -> str:
    if delta is None or abs(delta) < 0.01:
        return "stable"
    if higher_is_worse:
        return "worsening" if delta > 0 else "improving"
    return "worsening" if delta < 0 else "improving"


def _trend_arrow(direction: str) -> str:
    return {"improving": "↓", "worsening": "↑", "stable": "→"}[direction]


def _respiratory_at_hour(timeline: Dict[str, Any], hour: int, baseline: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = {
        "fio2": int(baseline.get("fio2", 21)),
        "peep": int(baseline.get("peep", 5)),
        "mechanical_ventilation": bool(baseline.get("mechanical_ventilation")),
    }
    for event in timeline.get("resp_events", []):
        if event["hour"] > hour:
            break
        label = str(event.get("label", "")).lower()
        value = _safe_float(event.get("value")) or 0
        if "fio2" in label:
            snapshot["fio2"] = int(min(100, value))
        elif "peep" in label:
            snapshot["peep"] = int(value)
    return snapshot


def compute_trends(
    snapshot: Dict[str, Any],
    timeline: Dict[str, Any],
    selected_hour: int,
    lookback: int = LOOKBACK_HOURS,
) -> List[Dict[str, Any]]:
    vitals = snapshot.get("vitals_history", [])
    compare_hour = max(0, selected_hour - lookback)
    current_v = snapshot.get("vitals_row", {})
    prior_v = _vitals_at_hour(vitals, compare_hour) or {}
    current_labs = snapshot.get("labs", {})
    prior_labs = _labs_at_hour(timeline, compare_hour)
    prior_resp = _respiratory_at_hour(timeline, compare_hour, snapshot.get("respiratory", {}))
    current_resp = snapshot.get("respiratory", {})

    specs = [
        ("SpO₂", "spo2", current_v.get("spo2"), prior_v.get("spo2"), "%", True),
        ("Heart rate", "heart_rate", current_v.get("heart_rate"), prior_v.get("heart_rate"), "bpm", True),
        ("Lactate", "Lactate", current_labs.get("Lactate"), prior_labs.get("Lactate"), "mmol/L", True),
        ("Creatinine", "Creatinine", current_labs.get("Creatinine"), prior_labs.get("Creatinine"), "mg/dL", True),
        ("FiO₂", "fio2", current_resp.get("fio2"), prior_resp.get("fio2"), "%", True),
    ]

    trends: List[Dict[str, Any]] = []
    for label, _key, current, prior, unit, higher_is_worse in specs:
        current_num = _safe_float(current)
        prior_num = _safe_float(prior)
        if current_num is None:
            continue

        delta = None
        if prior_num is not None:
            delta = round(current_num - prior_num, 2)

        direction = _trend_direction(delta, higher_is_worse=higher_is_worse)
        trends.append(
            {
                "label": label,
                "current": current_num,
                "prior": prior_num,
                "prior_hour": compare_hour if prior_num is not None else None,
                "delta": delta,
                "unit": unit,
                "direction": direction,
                "arrow": _trend_arrow(direction),
                "summary": _format_trend_summary(label, current_num, prior_num, compare_hour, unit, direction),
            }
        )

    return trends


def _format_trend_summary(
    label: str,
    current: float,
    prior: Optional[float],
    prior_hour: int,
    unit: str,
    direction: str,
) -> str:
    if prior is None:
        return f"{label}: {current} {unit} (no prior value in lookback window)"
    arrow = _trend_arrow(direction)
    return (
        f"{label}: {current} {unit} ({arrow} from {prior} at H{prior_hour}, "
        f"Δ {current - prior:+.2f})"
    )


def build_alerts(
    patient: PatientState,
    snapshot: Dict[str, Any],
    timeline: Dict[str, Any],
    selected_hour: int,
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    row = snapshot.get("vitals_row", {})
    labs = snapshot.get("labs", {})
    resp = snapshot.get("respiratory", {})
    vitals = snapshot.get("vitals_history", [])

    spo2 = _safe_float(row.get("spo2"))
    heart_rate = _safe_float(row.get("heart_rate"))
    lactate = _safe_float(labs.get("Lactate"))
    creatinine = _safe_float(labs.get("Creatinine"))
    fio2 = _safe_float(resp.get("fio2"))

    if spo2 is not None and spo2 < 85:
        alerts.append(
            _alert(
                "hypoxemia_critical",
                "critical",
                "Critical hypoxemia",
                f"SpO₂ {spo2:.0f}% is below 85%",
                "SpO₂ < 85%",
                _spo2_evidence(vitals, selected_hour),
            )
        )
    elif spo2 is not None and spo2 < 90:
        alerts.append(
            _alert(
                "hypoxemia",
                "warning",
                "Hypoxemia",
                f"SpO₂ {spo2:.0f}% is below 90%",
                "SpO₂ < 90%",
                _spo2_evidence(vitals, selected_hour),
            )
        )

    if heart_rate is not None and heart_rate > 125:
        alerts.append(
            _alert(
                "tachycardia_critical",
                "critical",
                "Severe tachycardia",
                f"Heart rate {heart_rate:.0f} bpm exceeds 125",
                "HR > 125 bpm",
                _vital_evidence(vitals, "heart_rate", selected_hour),
            )
        )
    elif heart_rate is not None and heart_rate > 115:
        alerts.append(
            _alert(
                "tachycardia",
                "warning",
                "Tachycardia",
                f"Heart rate {heart_rate:.0f} bpm exceeds 115",
                "HR > 115 bpm",
                _vital_evidence(vitals, "heart_rate", selected_hour),
            )
        )

    if lactate is not None and lactate > 4:
        alerts.append(
            _alert(
                "hyperlactatemia",
                "critical",
                "Hyperlactatemia / sepsis concern",
                f"Lactate {lactate:.1f} mmol/L exceeds 4.0",
                "Lactate > 4 mmol/L",
                _lab_evidence(timeline, "Lactate", selected_hour),
            )
        )
    elif lactate is not None and lactate > 2:
        rising = _lab_rising(timeline, "Lactate", selected_hour, threshold=0.5)
        if rising:
            alerts.append(
                _alert(
                    "rising_lactate",
                    "warning",
                    "Rising lactate",
                    f"Lactate {lactate:.1f} mmol/L with upward trend",
                    "Lactate rise > 0.5 in lookback window",
                    _lab_evidence(timeline, "Lactate", selected_hour),
                )
            )

    if creatinine is not None and creatinine > 2:
        alerts.append(
            _alert(
                "aki",
                "warning",
                "Acute kidney injury concern",
                f"Creatinine {creatinine:.1f} mg/dL exceeds 2.0",
                "Creatinine > 2 mg/dL",
                _lab_evidence(timeline, "Creatinine", selected_hour),
            )
        )

    if fio2 is not None and fio2 > 40 and spo2 is not None and spo2 < 92:
        alerts.append(
            _alert(
                "refractory_hypoxemia",
                "warning",
                "Hypoxemia despite elevated FiO₂",
                f"FiO₂ {fio2:.0f}% with SpO₂ {spo2:.0f}%",
                "FiO₂ > 40% and SpO₂ < 92%",
                [
                    {"hour": selected_hour, "text": f"FiO₂ {fio2:.0f}%, SpO₂ {spo2:.0f}%"},
                ],
            )
        )

    if not alerts and snapshot.get("severity") == "critical":
        alerts.append(
            _alert(
                "severity_critical",
                "critical",
                "Critical physiology",
                "Composite vitals meet critical severity thresholds",
                "Severity engine: critical",
                _spo2_evidence(vitals, selected_hour),
            )
        )

    return alerts


def _alert(
    alert_id: str,
    level: str,
    title: str,
    message: str,
    rule: str,
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "id": alert_id,
        "level": level,
        "title": title,
        "message": message,
        "rule": rule,
        "evidence": evidence,
    }


def _spo2_evidence(vitals: List[Dict[str, Any]], selected_hour: int) -> List[Dict[str, Any]]:
    return _vital_evidence(vitals, "spo2", selected_hour)


def _vital_evidence(vitals: List[Dict[str, Any]], key: str, selected_hour: int) -> List[Dict[str, Any]]:
    evidence = []
    for row in vitals[-6:]:
        hour = int(row.get("hour", 0))
        if hour > selected_hour:
            continue
        value = row.get(key)
        if value is not None:
            evidence.append({"hour": hour, "text": f"{key.replace('_', ' ').title()} {value}"})
    return evidence[-4:]


def _lab_evidence(timeline: Dict[str, Any], analyte: str, selected_hour: int) -> List[Dict[str, Any]]:
    evidence = []
    for event in timeline.get("lab_events", []):
        if event.get("analyte") == analyte and event["hour"] <= selected_hour:
            evidence.append(
                {
                    "hour": event["hour"],
                    "text": f"{analyte} {event['value']}",
                }
            )
    return evidence[-4:]


def _lab_rising(timeline: Dict[str, Any], analyte: str, selected_hour: int, threshold: float = 0.5) -> bool:
    values = [
        (event["hour"], float(event["value"]))
        for event in timeline.get("lab_events", [])
        if event.get("analyte") == analyte and event["hour"] <= selected_hour
    ]
    if len(values) < 2:
        return False
    compare_hour = max(0, selected_hour - LOOKBACK_HOURS)
    prior = [value for hour, value in values if hour <= compare_hour]
    if not prior:
        return False
    return values[-1][1] - prior[-1] >= threshold


def build_recommended_actions(
    snapshot: Dict[str, Any],
    alerts: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    alert_ids = {alert["id"] for alert in alerts}
    resp = snapshot.get("respiratory", {})
    fio2 = int(resp.get("fio2", 21))
    peep = int(resp.get("peep", 5))

    if "hypoxemia_critical" in alert_ids or "hypoxemia" in alert_ids:
        actions.append(
            {
                "priority": "high",
                "action": "Reassess oxygenation and ventilator settings (FiO₂ / PEEP)",
                "detail": f"Current FiO₂ {fio2}%, PEEP {peep}. Consider ABG and chest imaging.",
            }
        )
        if fio2 < 100:
            actions.append(
                {
                    "priority": "high",
                    "action": "Escalate respiratory support per protocol",
                    "detail": f"Suggested FiO₂ target 55–{min(100, fio2 + 15)}%, PEEP {min(18, peep + 2)} if tolerated.",
                }
            )

    if "hyperlactatemia" in alert_ids or "rising_lactate" in alert_ids:
        actions.extend(
            [
                {
                    "priority": "high",
                    "action": "Repeat lactate in 2–4 hours",
                    "detail": "Trend lactate to assess perfusion response.",
                },
                {
                    "priority": "high",
                    "action": "Reassess sepsis bundle / antibiotics",
                    "detail": "Review source control, cultures, and antibiotic timing.",
                },
                {
                    "priority": "medium",
                    "action": "Vasopressor readiness check",
                    "detail": "Evaluate MAP, fluid balance, and perfusion targets.",
                },
            ]
        )

    if "aki" in alert_ids:
        actions.append(
            {
                "priority": "medium",
                "action": "Review renal function and nephrotoxic medications",
                "detail": "Monitor urine output and avoid nephrotoxins where possible.",
            }
        )

    if "tachycardia_critical" in alert_ids or "tachycardia" in alert_ids:
        actions.append(
            {
                "priority": "medium",
                "action": "Evaluate hemodynamic status",
                "detail": "Assess volume status, perfusion, pain, and arrhythmia.",
            }
        )

    severity = snapshot.get("severity", "stable")
    if severity == "critical" and not actions:
        actions.append(
            {
                "priority": "high",
                "action": "ICU senior review and escalation checklist",
                "detail": "Patient meets critical severity at this time point.",
            }
        )

    if not actions:
        actions.append(
            {
                "priority": "low",
                "action": "Continue hourly monitoring and trend review",
                "detail": "No high-priority escalation triggers at this hour.",
            }
        )

    seen = set()
    unique_actions = []
    for item in actions:
        key = item["action"]
        if key not in seen:
            seen.add(key)
            unique_actions.append(item)
    return unique_actions


def detect_data_gaps(timeline: Dict[str, Any], selected_hour: int) -> List[str]:
    gaps = []
    lactate_hour = _last_lab_hour(timeline, "Lactate", selected_hour)
    if lactate_hour is None:
        gaps.append("No lactate recorded up to this hour")
    elif selected_hour - lactate_hour >= 6:
        gaps.append(f"Lactate last drawn at H{lactate_hour} (>6h ago)")

    vitals = timeline.get("vitals", [])
    if vitals:
        latest_vital_hour = max(int(row.get("hour", 0)) for row in vitals if int(row.get("hour", 0)) <= selected_hour)
        if selected_hour - latest_vital_hour >= 2:
            gaps.append(f"No vitals recorded since H{latest_vital_hour}")

    if not timeline.get("note_events"):
        gaps.append("No clinical notes in timeline")

    return gaps


def _overall_trajectory(trends: List[Dict[str, Any]]) -> str:
    if not trends:
        return "unknown"
    worsening = sum(1 for trend in trends if trend["direction"] == "worsening")
    improving = sum(1 for trend in trends if trend["direction"] == "improving")
    if worsening >= 2 and worsening > improving:
        return "deteriorating"
    if improving >= 2 and improving > worsening:
        return "improving"
    return "stable"


def build_sbar(
    patient: PatientState,
    snapshot: Dict[str, Any],
    selected_hour: int,
    trends: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    actions: List[Dict[str, str]],
    trajectory: str,
) -> Dict[str, str]:
    row = snapshot.get("vitals_row", {})
    labs = snapshot.get("labs", {})
    resp = snapshot.get("respiratory", {})
    risk = snapshot.get("risk_scores", {})

    situation = (
        f"{patient.age}y {patient.gender} · ICU hour {selected_hour} · "
        f"Severity {snapshot.get('severity', 'unknown').upper()} · "
        f"Diagnosis: {patient.diagnosis[:100]}"
    )
    background = (
        f"Stay {patient.patient_id}. "
        f"Mechanical ventilation: {'Yes' if resp.get('mechanical_ventilation') else 'No'}. "
        f"FiO₂ {resp.get('fio2', '—')}%, PEEP {resp.get('peep', '—')}."
    )
    trend_bits = [trend["summary"] for trend in trends[:4]]
    alert_bits = [f"{alert['title']}: {alert['message']}" for alert in alerts[:3]]
    assessment = (
        f"Overall trajectory: {trajectory}. "
        f"Mortality risk estimate {risk.get('mortality_risk', 0)}% (heuristic). "
        f"HR {row.get('heart_rate', '—')} bpm, SpO₂ {row.get('spo2', '—')}%, "
        f"Lactate {labs.get('Lactate', '—')} mmol/L."
    )
    if trend_bits:
        assessment += " Trends: " + "; ".join(trend_bits) + "."
    if alert_bits:
        assessment += " Alerts: " + "; ".join(alert_bits) + "."

    recommendation = "; ".join(action["action"] for action in actions[:4])
    return {
        "situation": situation,
        "background": background,
        "assessment": assessment,
        "recommendation": recommendation,
    }


def build_critical_brief(
    patient: PatientState,
    snapshot: Dict[str, Any],
    timeline: Dict[str, Any],
    selected_hour: int,
) -> Dict[str, Any]:
    trends = compute_trends(snapshot, timeline, selected_hour)
    alerts = build_alerts(patient, snapshot, timeline, selected_hour)
    actions = build_recommended_actions(snapshot, alerts)
    data_gaps = detect_data_gaps(timeline, selected_hour)
    trajectory = _overall_trajectory(trends)
    sbar = build_sbar(patient, snapshot, selected_hour, trends, alerts, actions, trajectory)

    return {
        "hour": selected_hour,
        "trajectory": trajectory,
        "sbar": sbar,
        "trends": trends,
        "alerts": alerts,
        "actions": actions,
        "data_gaps": data_gaps,
    }
