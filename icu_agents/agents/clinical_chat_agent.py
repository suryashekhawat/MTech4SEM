"""Interactive point-in-time clinical dialogue for doctor feedback."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from config import OPENAI_MODEL
from models.patient_state import PatientState


class ClinicalChatAgent:
    """Respond to doctor questions and feedback using snapshot context."""

    def __init__(self) -> None:
        self.model = OPENAI_MODEL

    def respond(
        self,
        user_message: str,
        patient: PatientState,
        snapshot: Dict[str, Any],
        hour: int,
        pit_narrative: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        message = (user_message or "").strip()
        if not message:
            return "Please enter a question or clinical note so I can respond."

        if os.environ.get("OPENAI_API_KEY"):
            try:
                return self._llm_respond(message, patient, snapshot, hour, pit_narrative, history or [])
            except Exception as exc:
                fallback = self._rule_respond(message, patient, snapshot, hour, pit_narrative)
                return (
                    f"{fallback}\n\n"
                    f"(Note: LLM unavailable — {exc.__class__.__name__}. Showing rule-based reply.)"
                )

        return self._rule_respond(message, patient, snapshot, hour, pit_narrative)

    def _build_context(
        self,
        patient: PatientState,
        snapshot: Dict[str, Any],
        hour: int,
        pit_narrative: str,
    ) -> str:
        row = snapshot["vitals_row"]
        labs = snapshot["labs"]
        resp = snapshot["respiratory"]
        risk = snapshot["risk_scores"]
        events = snapshot.get("events", [])[-6:]

        event_lines = "\n".join(
            f"- Hour {event['hour']} [{event.get('category', '?')}]: {event.get('summary', '')}"
            for event in events
        ) or "- No notable events recorded yet."

        return f"""
Point-in-time ICU context (hour {hour}):
- Patient: {patient.age}y {patient.gender}, stay {patient.patient_id}
- Diagnosis: {patient.diagnosis}
- Severity: {snapshot['severity']}
- Vitals: HR {row.get('heart_rate')} bpm, SpO2 {row.get('spo2')}%, RR {row.get('resp_rate')}/min, Temp {row.get('temperature')} F
- Labs (cumulative to hour {hour}): WBC {labs.get('WBC')}, Lactate {labs.get('Lactate')}, Creatinine {labs.get('Creatinine')}, Platelets {labs.get('Platelets')}
- Respiratory: MV={resp.get('mechanical_ventilation')}, FiO2 {resp.get('fio2')}%, PEEP {resp.get('peep')}
- Risk scores: {risk}
- Recent events:
{event_lines}

Current generated report:
{pit_narrative.strip()}
""".strip()

    def _llm_respond(
        self,
        user_message: str,
        patient: PatientState,
        snapshot: Dict[str, Any],
        hour: int,
        pit_narrative: str,
        history: List[Dict[str, str]],
    ) -> str:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        context = self._build_context(patient, snapshot, hour, pit_narrative)
        system = f"""You are an ICU clinical decision-support assistant in a research demo.
You are helping a doctor review a patient at ICU hour {hour}.

Rules:
- Use ONLY the patient data provided below. Do not invent labs, vitals, or events.
- Acknowledge doctor feedback explicitly (agreement, disagreement, or clarification).
- Be concise, structured, and clinically grounded.
- Offer differential reasoning and suggested next monitoring steps when asked.
- State clearly this is decision support, not a substitute for clinical judgment.
- If data is missing, say so instead of guessing.

{context}
"""

        messages: List[Any] = [SystemMessage(content=system)]
        for turn in history[-8:]:
            role = turn.get("role")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=user_message))

        llm = ChatOpenAI(model=self.model, temperature=0.2)
        response = llm.invoke(messages)
        return str(response.content).strip()

    def _rule_respond(
        self,
        user_message: str,
        patient: PatientState,
        snapshot: Dict[str, Any],
        hour: int,
        pit_narrative: str,
    ) -> str:
        text = user_message.lower()
        row = snapshot["vitals_row"]
        labs = snapshot["labs"]
        resp = snapshot["respiratory"]
        risk = snapshot["risk_scores"]
        severity = snapshot["severity"]

        if any(word in text for word in ("hello", "hi", "help")):
            return (
                f"I can discuss this patient at ICU hour {hour}. "
                "Ask about severity, trends, labs, respiratory support, or share your clinical feedback."
            )

        if "disagree" in text or "wrong" in text or "not correct" in text:
            return (
                "Thank you for the feedback. I have recorded clinician disagreement. "
                "Please specify which element differs (vitals trend, lactate, respiratory status, or risk score) "
                "so the assessment can be refined."
            )

        if "agree" in text or "looks correct" in text or "accurate" in text:
            return (
                "Thank you — noted as clinician agreement with the current assessment. "
                f"I will keep the {severity} severity label at hour {hour}. "
                "Document any change in plan in your note."
            )

        if "why" in text and ("severity" in text or severity in text or "critical" in text or "worsening" in text):
            reasons = []
            if row.get("spo2", 100) < 85:
                reasons.append(f"SpO₂ is {row.get('spo2')}% (< 85% critical threshold)")
            elif row.get("spo2", 100) < 90:
                reasons.append(f"SpO₂ is {row.get('spo2')}% (< 90% hypoxemia threshold)")
            if row.get("heart_rate", 0) > 125:
                reasons.append(f"Heart rate is {row.get('heart_rate')} bpm (> 125 critical threshold)")
            elif row.get("heart_rate", 0) > 115:
                reasons.append(f"Heart rate is {row.get('heart_rate')} bpm (> 115 tachycardia threshold)")
            if not reasons:
                reasons.append("Vitals are within configured stable thresholds at this hour.")
            return (
                f"Severity is **{severity}** at hour {hour} because:\n- "
                + "\n- ".join(reasons)
                + f"\n\nMortality risk estimate: {risk.get('mortality_risk', 0)}%."
            )

        if any(word in text for word in ("next step", "next steps", "recommend", "what should", "plan")):
            actions = ["Continue hourly vitals and trend review"]
            if row.get("spo2", 100) < 90:
                actions.append("Reassess oxygenation and ventilator settings (FiO₂/PEEP)")
            if labs.get("Lactate", 0) > 2:
                actions.append("Repeat lactate and evaluate perfusion / sepsis bundle")
            if labs.get("Creatinine", 0) > 2:
                actions.append("Review renal function and nephrotoxic medications")
            if severity == "critical":
                actions.append("Consider ICU senior review and escalation checklist")
            return "Suggested next steps at this time point:\n- " + "\n- ".join(actions)

        if "lactate" in text:
            value = labs.get("Lactate", "—")
            trend = "unknown"
            lab_events = [
                event for event in snapshot.get("events", []) if event.get("category") == "lab" and "Lactate" in event.get("summary", "")
            ]
            if len(lab_events) >= 2:
                trend = "rising" if lab_events[-1].get("hour", 0) >= lab_events[-2].get("hour", 0) else "mixed"
            interpretation = "within typical range"
            if isinstance(value, (int, float)) and value > 4:
                interpretation = "elevated — consider tissue hypoperfusion / sepsis"
            elif isinstance(value, (int, float)) and value > 2:
                interpretation = "borderline elevated — trend monitoring advised"
            return (
                f"Lactate at hour {hour}: **{value} mmol/L** ({interpretation}). "
                f"Lab trend: {trend}. "
                f"Mortality risk currently {risk.get('mortality_risk', 0)}%."
            )

        if any(word in text for word in ("spo2", "oxygen", "hypox", "vent", "fio2", "respiratory")):
            return (
                f"Respiratory status at hour {hour}:\n"
                f"- SpO₂: {row.get('spo2')}%\n"
                f"- RR: {row.get('resp_rate')}/min\n"
                f"- Mechanical ventilation: {resp.get('mechanical_ventilation')}\n"
                f"- FiO₂: {resp.get('fio2')}%, PEEP: {resp.get('peep')}\n\n"
                "If hypoxemia persists despite increased FiO₂, consider ABG, recruitment maneuvers, "
                "and evaluation for worsening shunt or fluid overload."
            )

        if "risk" in text or "mortality" in text:
            return (
                f"Risk scores at hour {hour}:\n"
                f"- Mortality risk: {risk.get('mortality_risk', 0)}%\n"
                f"- Sepsis risk: {risk.get('sepsis_risk', 0)}%\n"
                f"- ICU deterioration risk: {risk.get('icu_deterioration_risk', 0)}%\n\n"
                "These are heuristic demo scores based on vitals and labs, not validated clinical scores."
            )

        if "summarize" in text or "summary" in text:
            return pit_narrative.strip()

        # Match quoted clinical observations from the doctor.
        if re.search(r"\b(patient|i think|consider|believe|concerned)\b", text):
            return (
                "Clinical feedback noted. Based on available data at this hour, I can refine the assessment "
                "if you specify which finding you disagree with or what additional concern you have "
                "(e.g., 'I think patient is improving despite lactate'). "
                "Set OPENAI_API_KEY for richer conversational responses."
            )

        return (
            f"I received your note at ICU hour {hour}. "
            "Try asking: 'Why is severity critical?', 'What are the next steps?', "
            "'Explain the lactate trend', or share feedback like 'I disagree — patient is improving'. "
            "Set OPENAI_API_KEY for full LLM-backed dialogue."
        )
