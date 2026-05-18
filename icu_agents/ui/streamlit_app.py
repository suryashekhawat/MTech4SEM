import streamlit as st
import sys
from pathlib import Path

# Ensure project root is importable regardless of launch directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from orchestrator.patient_pipeline import PatientPipeline


st.title("ICU Multi-Agent Synthetic Patient Generator")

if st.button("Generate Synthetic ICU Patient"):
    pipeline = PatientPipeline()
    patient = pipeline.run()

    st.subheader("Patient Summary")
    st.write(patient.narrative)

    st.subheader("Vitals")
    st.json(patient.vitals)

    st.subheader("Labs")
    st.json(patient.labs)

    st.subheader("Risk Scores")
    st.json(patient.risk_scores)
