import sys
from pathlib import Path

import streamlit as st

# Ensure project root is importable regardless of launch directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config import DATA_SOURCE
from data.eicu_loader import list_stay_ids
from orchestrator.patient_pipeline import PatientPipeline


st.title("ICU Multi-Agent Patient Pipeline (eICU-CRD + Synthetic)")

source = st.sidebar.selectbox(
    "Data source",
    options=["eicu", "synthetic"],
    index=0 if DATA_SOURCE == "eicu" else 1,
)

stay_id = None
if source == "eicu":
    stays = list_stay_ids(100)
    stay_id = st.sidebar.selectbox("eICU patientunitstayid", options=stays)
    st.sidebar.caption("Loads vitals, labs, and notes from data/eicu-crd-demo SQLite.")

if st.button("Run ICU Pipeline"):
    pipeline = PatientPipeline()
    patient = pipeline.run(source=source, stay_id=stay_id)

    st.subheader("Patient Summary")
    st.write(patient.narrative)

    st.subheader("Metadata")
    st.json(
        {
            "data_source": source,
            "patient_id": patient.patient_id,
            "diagnosis": patient.diagnosis,
        }
    )

    st.subheader("Vitals")
    st.json(patient.vitals)

    st.subheader("Labs")
    st.json(patient.labs)

    st.subheader("Risk Scores")
    st.json(patient.risk_scores)
