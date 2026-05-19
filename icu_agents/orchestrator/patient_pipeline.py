import uuid
from typing import Optional

from agents.lab_agent import LabAgent
from agents.narrative_agent import NarrativeAgent
from agents.radiology_agent import RadiologyAgent
from agents.respiratory_agent import RespiratoryAgent
from agents.risk_agent import RiskAgent
from agents.vitals_agent import VitalsAgent
from config import DATA_SOURCE
from data.pipeline_source import build_patient_state
from models.patient_state import PatientState
from synthetic.clinical_rules import generate_base_patient


class PatientPipeline:
    def __init__(self):
        self.vitals_agent = VitalsAgent()
        self.lab_agent = LabAgent()
        self.radiology_agent = RadiologyAgent()
        self.respiratory_agent = RespiratoryAgent()
        self.risk_agent = RiskAgent()
        self.narrative_agent = NarrativeAgent()

    def run(
        self,
        source: Optional[str] = None,
        stay_id: Optional[int] = None,
    ) -> PatientState:
        mode = (source or DATA_SOURCE).lower()
        if mode == "eicu":
            return build_patient_state(source="eicu", stay_id=stay_id)

        base = generate_base_patient()
        patient = PatientState(
            patient_id=str(uuid.uuid4()),
            age=base["age"],
            gender=base["gender"],
            diagnosis=base["diagnosis"],
        )

        patient.vitals = self.vitals_agent.generate(patient.diagnosis)
        patient.labs = self.lab_agent.generate(patient.diagnosis)
        patient.radiology = self.radiology_agent.generate(patient.diagnosis)
        patient.respiratory = self.respiratory_agent.generate(patient.diagnosis)
        patient.risk_scores = self.risk_agent.calculate(patient.vitals, patient.labs)
        patient.narrative = self.narrative_agent.generate(patient)
        return patient
