class NarrativeAgent:
    def generate(self, patient):
        latest_vitals = patient.vitals[-1]

        narrative = f"""
Patient ID: {patient.patient_id}

{patient.age}-year-old {patient.gender} admitted with {patient.diagnosis}.

Vital signs demonstrate heart rate of {latest_vitals['heart_rate']} bpm,
temperature {latest_vitals['temperature']} F,
oxygen saturation {latest_vitals['spo2']}%.

Laboratory evaluation demonstrates WBC {patient.labs['WBC']} K/uL,
lactate {patient.labs['Lactate']} mmol/L,
and creatinine {patient.labs['Creatinine']} mg/dL.

Radiology Findings:
{patient.radiology['report']}

Respiratory Support:
Mechanical Ventilation = {patient.respiratory['mechanical_ventilation']}
FiO2 = {patient.respiratory['fio2']}%

Predicted Mortality Risk:
{patient.risk_scores['mortality_risk']}%

Clinical Impression:
Patient demonstrates ongoing critical illness requiring ICU-level monitoring.
"""

        return narrative
