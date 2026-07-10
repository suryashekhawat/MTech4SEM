from typing import List, Optional


class NarrativeAgent:
    def generate(
        self,
        patient,
        hour: Optional[int] = None,
        recent_events: Optional[List] = None,
    ):
        latest_vitals = patient.vitals[-1]
        hour_label = f" (ICU hour {hour})" if hour is not None else ""
        labs = patient.labs or {}
        respiratory = patient.respiratory or {}
        radiology = patient.radiology or {}
        risk = patient.risk_scores or {}

        event_block = ""
        if recent_events:
            notable = [
                event["summary"]
                for event in recent_events[-8:]
                if event.get("category") in ("lab", "note", "respiratory", "vitals")
            ]
            if notable:
                event_block = "\nRecent timeline events:\n- " + "\n- ".join(notable) + "\n"

        severity = "stable"
        if latest_vitals.get("spo2", 100) < 85 or latest_vitals.get("heart_rate", 80) > 125:
            severity = "critical"
        elif latest_vitals.get("spo2", 100) < 90 or latest_vitals.get("heart_rate", 80) > 115:
            severity = "worsening"

        impression = {
            "stable": "Patient remains hemodynamically stable with ICU-level monitoring.",
            "worsening": "Patient shows early signs of physiologic deterioration requiring closer monitoring.",
            "critical": "Patient demonstrates critical illness with high-acuity ICU management needs.",
        }[severity]

        narrative = f"""
Patient ID: {patient.patient_id}{hour_label}

{patient.age}-year-old {patient.gender} admitted with {patient.diagnosis}.

Vital signs at this time point demonstrate heart rate of {latest_vitals['heart_rate']} bpm,
temperature {latest_vitals['temperature']} F,
oxygen saturation {latest_vitals['spo2']}%.

Laboratory evaluation demonstrates WBC {labs.get('WBC', '—')} K/uL,
lactate {labs.get('Lactate', '—')} mmol/L,
and creatinine {labs.get('Creatinine', '—')} mg/dL.
{event_block}
Radiology / clinical notes:
{radiology.get('report', 'No notes available at this time point.')}

Respiratory Support:
Mechanical Ventilation = {respiratory.get('mechanical_ventilation', False)}
FiO2 = {respiratory.get('fio2', '—')}%

Predicted Mortality Risk:
{risk.get('mortality_risk', 0)}%

Clinical Impression ({severity}):
{impression}
"""

        return narrative
