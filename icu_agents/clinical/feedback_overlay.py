"""Apply doctor dialogue to adjust clinical brief and expose before/after impact."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple


def _doctor_messages(history: List[Dict[str, str]]) -> List[str]:
    return [msg["content"] for msg in history if msg.get("role") == "user"]


def _contains_any(text: str, phrases: Tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _classify_feedback(messages: List[str]) -> Dict[str, Any]:
    combined = " ".join(messages).lower()
    flags = {
        "disagrees": _contains_any(combined, ("disagree", "wrong", "not correct", "inaccurate")),
        "agrees": _contains_any(combined, ("agree", "looks correct", "accurate", "confirmed")),
        "improving": _contains_any(
            combined,
            ("improving", "better", "stabiliz", "recovering", "turning the corner"),
        ),
        "worsening": _contains_any(
            combined,
            ("worsening", "deteriorat", "declining", " crashing", " unstable"),
        ),
        "respiratory_plan": _contains_any(
            combined,
            ("increase peep", "increase fio2", "increase fi o2", "recruitment", "abg", "vent adjustment"),
        ),
        "sepsis_plan": _contains_any(
            combined,
            ("antibiotic", "sepsis bundle", "repeat lactate", "vasopressor", "fluid bolus"),
        ),
        "renal_plan": _contains_any(
            combined,
            ("hold diuretic", "nephotox", "renal", "creatinine", "fluid restrictive", "hold fluids"),
        ),
        "deescalate": _contains_any(
            combined,
            ("wean", "de-escalat", "deescalat", "reduce fio2", "extubation", "less aggressive"),
        ),
        "senior_review": _contains_any(combined, ("senior review", "attending", "consult", "icu fellow")),
    }
    flags["messages"] = messages
    flags["combined"] = combined
    return flags


def _remove_alerts_by_keyword(alerts: List[Dict[str, Any]], keywords: Tuple[str, ...]) -> List[Dict[str, Any]]:
    kept = []
    for alert in alerts:
        blob = f"{alert.get('id', '')} {alert.get('title', '')} {alert.get('message', '')}".lower()
        if any(keyword in blob for keyword in keywords):
            continue
        kept.append(alert)
    return kept


def _add_action(actions: List[Dict[str, str]], action: str, detail: str, priority: str = "high") -> None:
    if any(item["action"] == action for item in actions):
        return
    actions.insert(0, {"priority": priority, "action": action, "detail": detail, "source": "clinician"})


def apply_doctor_feedback(
    brief: Dict[str, Any],
    chat_history: List[Dict[str, str]],
    snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Return clinician-adjusted brief and an impact summary. Baseline brief is unchanged."""
    messages = _doctor_messages(chat_history)
    if not messages:
        return brief, None

    flags = _classify_feedback(messages)
    adjusted = copy.deepcopy(brief)
    impact: Dict[str, Any] = {
        "has_feedback": True,
        "doctor_turns": len(messages),
        "trajectory_before": brief.get("trajectory", "unknown"),
        "trajectory_after": brief.get("trajectory", "unknown"),
        "severity_before": snapshot.get("severity", "unknown") if snapshot else "unknown",
        "severity_after": snapshot.get("severity", "unknown") if snapshot else "unknown",
        "alerts_before": len(brief.get("alerts", [])),
        "alerts_after": len(brief.get("alerts", [])),
        "actions_before": [a["action"] for a in brief.get("actions", [])],
        "actions_after": [],
        "actions_added": [],
        "actions_removed": [],
        "alerts_acknowledged": [],
        "alerts_overridden": [],
        "feedback_notes": [],
        "confidence": "automated",
    }

    trajectory = brief.get("trajectory", "stable")
    alerts = list(adjusted.get("alerts", []))
    actions = list(adjusted.get("actions", []))

    if flags["agrees"]:
        impact["feedback_notes"].append("Clinician confirmed the automated assessment.")
        impact["confidence"] = "clinician-confirmed"

    if flags["disagrees"] and flags["improving"]:
        trajectory = "improving"
        impact["feedback_notes"].append(
            "Clinician disagrees with deterioration view — bedside assessment suggests improvement."
        )
        impact["confidence"] = "clinician-adjusted"
        alerts = _remove_alerts_by_keyword(alerts, ("tachycardia", "hypoxemia", "severity"))
        impact["alerts_overridden"].extend(
            [alert["title"] for alert in brief.get("alerts", []) if alert not in alerts]
        )
        _add_action(
            actions,
            "Continue current plan with focused reassessment in 2–4 hours",
            "Escalation deferred based on clinician bedside judgment.",
            priority="medium",
        )
        _add_action(
            actions,
            "Document clinician override in chart",
            "Record why automated alerts were downgraded.",
            priority="low",
        )

    elif flags["disagrees"]:
        impact["feedback_notes"].append(
            "Clinician challenged the automated assessment — review specific findings together."
        )
        impact["confidence"] = "clinician-review-needed"
        _add_action(
            actions,
            "Clarify disputed findings with clinician",
            "Identify whether vitals, labs, or respiratory data drive disagreement.",
            priority="high",
        )

    if flags["worsening"] and not flags["improving"]:
        trajectory = "deteriorating"
        impact["feedback_notes"].append("Clinician reports clinical worsening at the bedside.")
        impact["confidence"] = "clinician-adjusted"
        _add_action(
            actions,
            "Escalate monitoring frequency to q30–60 min",
            "Bedside concern for deterioration despite partial data alignment.",
            priority="high",
        )
        if flags["senior_review"]:
            _add_action(
                actions,
                "Request ICU senior / attending review now",
                "Explicitly requested in clinician dialogue.",
                priority="high",
            )

    if flags["respiratory_plan"]:
        impact["feedback_notes"].append("Clinician requested respiratory plan adjustment.")
        _add_action(
            actions,
            "Execute respiratory plan per clinician note",
            "Review ABG, compliance, and FiO₂/PEEP targets discussed in dialogue.",
            priority="high",
        )

    if flags["sepsis_plan"]:
        impact["feedback_notes"].append("Clinician requested sepsis / perfusion interventions.")
        _add_action(
            actions,
            "Execute sepsis bundle actions per clinician note",
            "Includes lactate monitoring, antibiotics, and perfusion reassessment as documented.",
            priority="high",
        )

    if flags["renal_plan"]:
        impact["feedback_notes"].append("Clinician flagged renal / fluid management concern.")
        _add_action(
            actions,
            "Adjust fluid and renal management per clinician note",
            "Review creatinine trend, urine output, and nephrotoxic medications.",
            priority="medium",
        )

    if flags["deescalate"]:
        trajectory = "improving" if trajectory != "deteriorating" else trajectory
        impact["feedback_notes"].append("Clinician supports de-escalation when safe.")
        _add_action(
            actions,
            "Plan de-escalation trial with close monitoring",
            "Weaning FiO₂ / vent support only if vitals and perfusion remain acceptable.",
            priority="medium",
        )

    for message in messages:
        if re.search(r"\b(start|hold|stop|increase|decrease)\b", message.lower()):
            snippet = message.strip()[:160]
            if snippet not in impact["feedback_notes"]:
                impact["feedback_notes"].append(f"Clinician plan captured: “{snippet}”")

    before_actions = set(impact["actions_before"])
    after_actions = [a["action"] for a in actions]
    impact["actions_added"] = [a for a in after_actions if a not in before_actions]
    impact["actions_removed"] = [a for a in before_actions if a not in after_actions]
    impact["actions_after"] = after_actions
    impact["alerts_after"] = len(alerts)
    impact["trajectory_after"] = trajectory

    sbar = dict(adjusted.get("sbar", {}))
    if impact["feedback_notes"]:
        note = " Clinician feedback applied: " + " ".join(impact["feedback_notes"][:2])
        sbar["assessment"] = (sbar.get("assessment", "") + note).strip()
        if impact["actions_added"]:
            sbar["recommendation"] = "; ".join(after_actions[:5])

    adjusted["trajectory"] = trajectory
    adjusted["alerts"] = alerts
    adjusted["actions"] = actions
    adjusted["sbar"] = sbar
    adjusted["clinician_adjusted"] = True
    adjusted["feedback_confidence"] = impact["confidence"]

    return adjusted, impact
