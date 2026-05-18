from __future__ import annotations

import json
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from airflow.decorators import dag, task
from airflow.utils.trigger_rule import TriggerRule

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


OUTPUT_TIMELINES = PROJECT_ROOT / "output" / "timelines"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"


@dag(
    dag_id="icu_temporal_reasoning_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["icu", "temporal", "reasoning", "branching"],
)
def icu_temporal_reasoning_pipeline():
    @task
    def generate_temporal_bundle(hours: int = 24) -> Dict[str, Any]:
        base = generate_base_patient()

        patient = {
            "patient_id": str(uuid.uuid4()),
            "age": base["age"],
            "gender": base["gender"],
            "diagnosis": base["diagnosis"],
        }

        vitals = VitalsAgent().generate(patient["diagnosis"], hours=hours)
        labs = LabAgent().generate(patient["diagnosis"])
        radiology = RadiologyAgent().generate(patient["diagnosis"])
        respiratory = RespiratoryAgent().generate(patient["diagnosis"])
        risk_scores = RiskAgent().calculate(vitals, labs)

        return {
            **patient,
            "hours": hours,
            "vitals": vitals,
            "labs": labs,
            "radiology": radiology,
            "respiratory": respiratory,
            "risk_scores": risk_scores,
        }

    @task
    def build_hourly_reasoning_trace(bundle: Dict[str, Any]) -> Dict[str, Any]:
        trace: List[Dict[str, Any]] = []
        for hour, row in enumerate(bundle["vitals"]):
            severity = "stable"
            if row["spo2"] < 90 or row["heart_rate"] > 115:
                severity = "worsening"
            if row["spo2"] < 85 or row["heart_rate"] > 125:
                severity = "critical"

            trace.append(
                {
                    "hour": hour + 1,
                    "spo2": row["spo2"],
                    "heart_rate": row["heart_rate"],
                    "resp_rate": row["resp_rate"],
                    "severity": severity,
                }
            )

        bundle["reasoning_trace"] = trace
        return bundle

    @task.branch
    def branch_hypoxia(bundle: Dict[str, Any]) -> str:
        latest = bundle["vitals"][-1]
        if latest["spo2"] < 85:
            return "trigger_respiratory_escalation"
        return "skip_respiratory_escalation"

    @task.branch
    def branch_septic_shock(bundle: Dict[str, Any]) -> str:
        if bundle["labs"]["Lactate"] > 4:
            return "trigger_sepsis_escalation"
        return "skip_sepsis_escalation"

    @task
    def trigger_respiratory_escalation(bundle: Dict[str, Any]) -> None:
        _ = bundle

    @task
    def skip_respiratory_escalation(bundle: Dict[str, Any]) -> None:
        _ = bundle

    @task
    def trigger_sepsis_escalation(bundle: Dict[str, Any]) -> None:
        _ = bundle

    @task
    def skip_sepsis_escalation(bundle: Dict[str, Any]) -> None:
        _ = bundle

    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def coordinator_agent(bundle: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(bundle)
        latest = merged["vitals"][-1]
        hypoxia_triggered = latest["spo2"] < 85
        sepsis_triggered = merged["labs"]["Lactate"] > 4

        merged["respiratory_escalation"] = {
            "triggered": hypoxia_triggered,
            "reason": "SpO2 below 85%" if hypoxia_triggered else "SpO2 threshold not crossed",
            "recommended_fio2": (
                min(100, int(merged["respiratory"]["fio2"]) + random.randint(5, 15))
                if hypoxia_triggered
                else merged["respiratory"]["fio2"]
            ),
            "recommended_peep": (
                min(18, int(merged["respiratory"]["peep"]) + random.randint(2, 4))
                if hypoxia_triggered
                else merged["respiratory"]["peep"]
            ),
        }

        merged["sepsis_escalation"] = {
            "triggered": sepsis_triggered,
            "reason": "Lactate above 4 mmol/L" if sepsis_triggered else "Lactate threshold not crossed",
            "recommended_actions": (
                [
                    "repeat lactate in 2 hours",
                    "broad-spectrum antibiotics reassessment",
                    "vasopressor readiness check",
                ]
                if sepsis_triggered
                else []
            ),
        }

        merged["coordinator_summary"] = {
            "respiratory_path": merged.get("respiratory_escalation", {}).get("reason"),
            "sepsis_path": merged.get("sepsis_escalation", {}).get("reason"),
            "current_mortality_risk": merged["risk_scores"]["mortality_risk"],
        }
        return merged

    @task
    def optional_langgraph_handoff(bundle: Dict[str, Any], enabled: bool = False) -> Dict[str, Any]:
        # Placeholder for future LangGraph state-machine integration.
        bundle["langgraph_handoff"] = {
            "enabled": enabled,
            "status": "skipped" if not enabled else "ready_for_integration",
        }
        return bundle

    @task
    def generate_temporal_narrative(bundle: Dict[str, Any]) -> Dict[str, Any]:
        latest = bundle["vitals"][-1]
        critical_hours = [x["hour"] for x in bundle["reasoning_trace"] if x["severity"] == "critical"]

        narrative = f"""
Patient ID: {bundle['patient_id']}
Diagnosis: {bundle['diagnosis']}

Temporal ICU reasoning completed over {bundle['hours']} hours.
Latest status: HR {latest['heart_rate']} bpm, SpO2 {latest['spo2']}%, RR {latest['resp_rate']}.
Mortality risk estimate: {bundle['risk_scores']['mortality_risk']}%.

Respiratory escalation triggered: {bundle['respiratory_escalation']['triggered']}
Sepsis escalation triggered: {bundle['sepsis_escalation']['triggered']}

Critical timeline hours: {critical_hours if critical_hours else 'none'}.
Coordinator recommendation: continue ICU-level monitoring with dynamic reassessment.
""".strip()

        bundle["temporal_narrative"] = narrative
        return bundle

    @task
    def store_temporal_outputs(bundle: Dict[str, Any]) -> None:
        OUTPUT_TIMELINES.mkdir(parents=True, exist_ok=True)
        OUTPUT_REPORTS.mkdir(parents=True, exist_ok=True)

        timeline_path = OUTPUT_TIMELINES / f"{bundle['patient_id']}_temporal_trace.json"
        report_path = OUTPUT_REPORTS / f"{bundle['patient_id']}_temporal_report.txt"

        with timeline_path.open("w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        with report_path.open("w", encoding="utf-8") as f:
            f.write(bundle["temporal_narrative"])

    initial = generate_temporal_bundle()
    traced = build_hourly_reasoning_trace(initial)

    hypoxia_choice = branch_hypoxia(traced)
    sepsis_choice = branch_septic_shock(traced)

    respiratory_on = trigger_respiratory_escalation(traced)
    respiratory_off = skip_respiratory_escalation(traced)
    hypoxia_choice >> [respiratory_on, respiratory_off]

    sepsis_on = trigger_sepsis_escalation(traced)
    sepsis_off = skip_sepsis_escalation(traced)
    sepsis_choice >> [sepsis_on, sepsis_off]

    merged = coordinator_agent(traced)
    [respiratory_on, respiratory_off, sepsis_on, sepsis_off] >> merged
    with_handoff = optional_langgraph_handoff(merged)
    final_bundle = generate_temporal_narrative(with_handoff)
    store_temporal_outputs(final_bundle)


icu_temporal_reasoning_pipeline_dag = icu_temporal_reasoning_pipeline()
