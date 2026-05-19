from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from airflow.decorators import dag, task
from airflow.utils.trigger_rule import TriggerRule

# Make project modules importable when DAG is loaded by Airflow.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config import DATA_SOURCE
from data.pipeline_source import build_patient_dict


OUTPUT_TIMELINES = PROJECT_ROOT / "output" / "timelines"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"


@dag(
    dag_id="icu_temporal_reasoning_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["icu", "eicu", "temporal", "reasoning", "branching"],
)
def icu_temporal_reasoning_pipeline():
    @task
    def load_temporal_bundle() -> Dict[str, Any]:
        source = os.environ.get("ICU_DATA_SOURCE", DATA_SOURCE)
        bundle = build_patient_dict(source=source)
        bundle["hours"] = len(bundle.get("vitals", [])) or 24
        return bundle

    @task
    def build_hourly_reasoning_trace(bundle: Dict[str, Any]) -> Dict[str, Any]:
        trace: List[Dict[str, Any]] = []
        for hour, row in enumerate(bundle["vitals"]):
            severity = "stable"
            spo2 = row.get("spo2", 100)
            heart_rate = row.get("heart_rate", 80)
            if spo2 < 90 or heart_rate > 115:
                severity = "worsening"
            if spo2 < 85 or heart_rate > 125:
                severity = "critical"

            trace.append(
                {
                    "hour": hour + 1,
                    "spo2": spo2,
                    "heart_rate": heart_rate,
                    "resp_rate": row.get("resp_rate"),
                    "severity": severity,
                    "reason": (
                        f"SpO2={spo2}%, HR={heart_rate} evaluated against ICU thresholds"
                    ),
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
            "reason": "SpO2 below 85% on eICU-derived trace"
            if hypoxia_triggered
            else "SpO2 threshold not crossed",
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
            "reason": "Lactate above 4 mmol/L on eICU lab panel"
            if sepsis_triggered
            else "Lactate threshold not crossed",
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
            "data_source": merged.get("data_source"),
            "respiratory_path": merged.get("respiratory_escalation", {}).get("reason"),
            "sepsis_path": merged.get("sepsis_escalation", {}).get("reason"),
            "current_mortality_risk": merged["risk_scores"]["mortality_risk"],
        }
        return merged

    @task
    def optional_langgraph_handoff(bundle: Dict[str, Any], enabled: bool = False) -> Dict[str, Any]:
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
Data source: {bundle.get('data_source', 'unknown')}
Diagnosis: {bundle['diagnosis']}

Temporal ICU reasoning completed over {bundle['hours']} hourly observations from eICU-CRD demo vitals.
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

    initial = load_temporal_bundle()
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
