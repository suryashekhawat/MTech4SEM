"""Build patient bundles from eICU-CRD demo or synthetic generators."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from agents.lab_agent import LabAgent
from agents.narrative_agent import NarrativeAgent
from agents.radiology_agent import RadiologyAgent
from agents.respiratory_agent import RespiratoryAgent
from agents.risk_agent import RiskAgent
from agents.vitals_agent import VitalsAgent
from config import DATA_SOURCE, MAX_ICU_HOURS, SEED
from data.eicu_loader import load_patient_state, patient_state_to_dict, sample_stay_id
from models.patient_state import PatientState
from synthetic.clinical_rules import generate_base_patient


def _fill_synthetic_gaps(patient: PatientState) -> PatientState:
    diagnosis = patient.diagnosis or "Sepsis"
    if not patient.vitals:
        patient.vitals = VitalsAgent().generate(diagnosis, hours=min(24, MAX_ICU_HOURS))
    if not patient.labs or all(v == 0 for v in patient.labs.values()):
        patient.labs = LabAgent().generate(diagnosis)
    if patient.radiology.get("source") == "eicu_placeholder":
        patient.radiology = RadiologyAgent().generate(diagnosis)
        patient.radiology["source"] = "synthetic_fallback"
    if patient.respiratory.get("fio2", 0) <= 0:
        patient.respiratory = RespiratoryAgent().generate(diagnosis)
        patient.respiratory["source"] = "synthetic_fallback"
    return patient


def build_patient_state(
    source: Optional[str] = None,
    stay_id: Optional[int] = None,
) -> PatientState:
    mode = (source or DATA_SOURCE).lower()

    if mode == "eicu":
        selected_stay = stay_id if stay_id is not None else sample_stay_id(SEED)
        patient = load_patient_state(int(selected_stay))
        patient = _fill_synthetic_gaps(patient)
    else:
        base = generate_base_patient()
        patient = PatientState(
            patient_id=str(uuid.uuid4()),
            age=base["age"],
            gender=base["gender"],
            diagnosis=base["diagnosis"],
        )
        patient.vitals = VitalsAgent().generate(patient.diagnosis, hours=min(24, MAX_ICU_HOURS))
        patient.labs = LabAgent().generate(patient.diagnosis)
        patient.radiology = RadiologyAgent().generate(patient.diagnosis)
        patient.respiratory = RespiratoryAgent().generate(patient.diagnosis)

    patient.risk_scores = RiskAgent().calculate(patient.vitals, patient.labs)
    patient.narrative = NarrativeAgent().generate(patient)
    return patient


def build_patient_dict(
    source: Optional[str] = None,
    stay_id: Optional[int] = None,
) -> Dict[str, Any]:
    patient = build_patient_state(source=source, stay_id=stay_id)
    tag = (source or DATA_SOURCE).lower()
    return patient_state_to_dict(patient, data_source=tag)
