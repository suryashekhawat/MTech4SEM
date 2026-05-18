from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from airflow.decorators import dag, task

# Make project modules importable when DAG is loaded by Airflow.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from agents.lab_agent import LabAgent
from agents.radiology_agent import RadiologyAgent
from agents.respiratory_agent import RespiratoryAgent
from agents.risk_agent import RiskAgent
from agents.vitals_agent import VitalsAgent
from synthetic.clinical_rules import generate_base_patient


OUTPUT_JSON = PROJECT_ROOT / "output" / "json"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"
OUTPUT_TIMELINES = PROJECT_ROOT / "output" / "timelines"


@dag(
    dag_id="icu_multi_agent_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["icu", "synthetic", "multi-agent"],
)
def icu_multi_agent_pipeline():
    @task
    def generate_patient() -> Dict[str, Any]:
        base = generate_base_patient()
        return {
            "patient_id": str(uuid.uuid4()),
            "age": base["age"],
            "gender": base["gender"],
            "diagnosis": base["diagnosis"],
        }

    @task
    def generate_vitals(state: Dict[str, Any]) -> Dict[str, Any]:
        state["vitals"] = VitalsAgent().generate(state["diagnosis"], hours=24)
        return state

    @task
    def generate_labs(state: Dict[str, Any]) -> Dict[str, Any]:
        state["labs"] = LabAgent().generate(state["diagnosis"])
        return state

    @task
    def generate_radiology(state: Dict[str, Any]) -> Dict[str, Any]:
        state["radiology"] = RadiologyAgent().generate(state["diagnosis"])
        return state

    @task
    def generate_respiratory(state: Dict[str, Any]) -> Dict[str, Any]:
        state["respiratory"] = RespiratoryAgent().generate(state["diagnosis"])
        return state

    @task
    def calculate_risk(state: Dict[str, Any]) -> Dict[str, Any]:
        state["risk_scores"] = RiskAgent().calculate(state["vitals"], state["labs"])
        return state

    @task
    def generate_narrative(state: Dict[str, Any]) -> Dict[str, Any]:
        latest_vitals = state["vitals"][-1]
        narrative = f"""
Patient ID: {state['patient_id']}

{state['age']}-year-old {state['gender']} admitted with {state['diagnosis']}.

Vital signs demonstrate heart rate of {latest_vitals['heart_rate']} bpm,
temperature {latest_vitals['temperature']} F,
oxygen saturation {latest_vitals['spo2']}%.

Laboratory evaluation demonstrates WBC {state['labs']['WBC']} K/uL,
lactate {state['labs']['Lactate']} mmol/L,
and creatinine {state['labs']['Creatinine']} mg/dL.

Radiology Findings:
{state['radiology']['report']}

Respiratory Support:
Mechanical Ventilation = {state['respiratory']['mechanical_ventilation']}
FiO2 = {state['respiratory']['fio2']}%

Predicted Mortality Risk:
{state['risk_scores']['mortality_risk']}%

Clinical Impression:
Patient demonstrates ongoing critical illness requiring ICU-level monitoring.
""".strip()
        state["narrative"] = narrative
        return state

    @task
    def store_patient_bundle(state: Dict[str, Any]) -> Dict[str, Any]:
        OUTPUT_JSON.mkdir(parents=True, exist_ok=True)
        OUTPUT_REPORTS.mkdir(parents=True, exist_ok=True)

        bundle_path = OUTPUT_JSON / f"{state['patient_id']}.json"
        report_path = OUTPUT_REPORTS / f"{state['patient_id']}.txt"

        with bundle_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        with report_path.open("w", encoding="utf-8") as f:
            f.write(state["narrative"])

        state["bundle_path"] = str(bundle_path)
        state["report_path"] = str(report_path)
        return state

    @task
    def update_dashboard(state: Dict[str, Any]) -> None:
        OUTPUT_TIMELINES.mkdir(parents=True, exist_ok=True)
        dashboard_payload = {
            "patient_id": state["patient_id"],
            "diagnosis": state["diagnosis"],
            "mortality_risk": state["risk_scores"]["mortality_risk"],
            "latest_spo2": state["vitals"][-1]["spo2"],
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "bundle_path": state.get("bundle_path"),
            "report_path": state.get("report_path"),
        }

        dashboard_file = OUTPUT_TIMELINES / "latest_dashboard.json"
        with dashboard_file.open("w", encoding="utf-8") as f:
            json.dump(dashboard_payload, f, indent=2)

    patient = generate_patient()
    vitals = generate_vitals(patient)
    labs = generate_labs(vitals)
    radiology = generate_radiology(labs)
    respiratory = generate_respiratory(radiology)
    risk = calculate_risk(respiratory)
    narrative = generate_narrative(risk)
    stored = store_patient_bundle(narrative)
    update_dashboard(stored)


icu_multi_agent_pipeline_dag = icu_multi_agent_pipeline()
