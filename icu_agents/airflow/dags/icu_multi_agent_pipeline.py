from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from airflow.decorators import dag, task

# Make project modules importable when DAG is loaded by Airflow.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config import DATA_SOURCE
from data.pipeline_source import build_patient_dict


OUTPUT_JSON = PROJECT_ROOT / "output" / "json"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"
OUTPUT_TIMELINES = PROJECT_ROOT / "output" / "timelines"


@dag(
    dag_id="icu_multi_agent_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["icu", "eicu", "multi-agent", "reasoning"],
)
def icu_multi_agent_pipeline():
    @task
    def load_patient_from_source() -> Dict[str, Any]:
        source = os.environ.get("ICU_DATA_SOURCE", DATA_SOURCE)
        return build_patient_dict(source=source)

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
        latest_vitals = state["vitals"][-1] if state.get("vitals") else {}
        dashboard_payload = {
            "patient_id": state["patient_id"],
            "data_source": state.get("data_source", DATA_SOURCE),
            "eicu_stay_id": state.get("eicu_stay_id"),
            "diagnosis": state["diagnosis"],
            "mortality_risk": state["risk_scores"]["mortality_risk"],
            "latest_spo2": latest_vitals.get("spo2"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "bundle_path": state.get("bundle_path"),
            "report_path": state.get("report_path"),
        }

        dashboard_file = OUTPUT_TIMELINES / "latest_dashboard.json"
        with dashboard_file.open("w", encoding="utf-8") as f:
            json.dump(dashboard_payload, f, indent=2)

    bundle = load_patient_from_source()
    stored = store_patient_bundle(bundle)
    update_dashboard(stored)


icu_multi_agent_pipeline_dag = icu_multi_agent_pipeline()
