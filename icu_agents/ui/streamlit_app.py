import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# Ensure project root is importable regardless of launch directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config import DATA_SOURCE
from data.eicu_loader import list_stay_ids
from models.patient_state import PatientState
from orchestrator.patient_pipeline import PatientPipeline


def vitals_dataframe(vitals: list) -> pd.DataFrame:
    df = pd.DataFrame(vitals)
    if "timestamp" in df.columns:
        df = df.rename(columns={"timestamp": "hour"})
    elif "hour" not in df.columns:
        df["hour"] = range(len(df))
    df = df.sort_values("hour").reset_index(drop=True)
    for col in ("heart_rate", "spo2", "resp_rate", "temperature", "systolic_bp"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def plot_vitals_matplotlib(df: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    hours = df["hour"]

    axes[0].plot(hours, df["heart_rate"], marker="o", color="#e74c3c", linewidth=2, label="Heart rate")
    axes[0].axhline(120, color="#e74c3c", linestyle="--", alpha=0.4, label="Tachycardia (120)")
    axes[0].set_ylabel("bpm")
    axes[0].set_title("Heart rate")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(hours, df["spo2"], marker="o", color="#3498db", linewidth=2, label="SpO₂")
    axes[1].axhline(90, color="#f39c12", linestyle="--", alpha=0.5, label="Hypoxemia (90%)")
    axes[1].axhline(85, color="#e74c3c", linestyle="--", alpha=0.5, label="Severe (85%)")
    axes[1].set_ylabel("%")
    axes[1].set_title("Oxygen saturation")
    axes[1].legend(loc="lower right", fontsize=8)
    axes[1].grid(True, alpha=0.3)

    if "resp_rate" in df.columns:
        axes[2].plot(hours, df["resp_rate"], marker="o", color="#9b59b6", linewidth=2, label="Resp rate")
        axes[2].set_ylabel("/min")
    if "systolic_bp" in df.columns:
        ax_bp = axes[2].twinx()
        ax_bp.plot(hours, df["systolic_bp"], marker="s", color="#16a085", linewidth=1.5, alpha=0.8, label="SBP")
        ax_bp.set_ylabel("SBP (mmHg)", color="#16a085")
    axes[2].set_xlabel("Hour (ICU stay offset)")
    axes[2].set_title("Respiratory rate & blood pressure")
    axes[2].grid(True, alpha=0.3)

    fig.suptitle("ICU vital signs — time series", fontsize=12, fontweight="bold")
    plt.tight_layout()
    return fig


def lab_within_screen(name: str, value: float) -> bool:
    checks = {
        "Lactate": value <= 4,
        "WBC": value <= 15,
        "Creatinine": value <= 2,
        "Platelets": value >= 100,
        "Hemoglobin": value >= 7,
    }
    return checks.get(name, True)


st.set_page_config(page_title="ICU Pipeline", layout="wide")
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

if st.sidebar.button("Run ICU Pipeline", type="primary"):
    with st.spinner("Running agents on patient data…"):
        pipeline = PatientPipeline()
        st.session_state.patient = pipeline.run(source=source, stay_id=stay_id)
        st.session_state.data_source = source

if "patient" not in st.session_state:
    st.info("Select options in the sidebar and click **Run ICU Pipeline** to load data and charts.")
    st.stop()

patient: PatientState = st.session_state.patient
data_source = st.session_state.get("data_source", source)

latest_spo2 = patient.vitals[-1].get("spo2") if patient.vitals else "—"
resp = patient.respiratory or {}

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Stay / ID", patient.patient_id)
col2.metric("Age / Gender", f"{patient.age} · {patient.gender}")
col3.metric("Mortality risk", f"{patient.risk_scores.get('mortality_risk', 0)}%")
col4.metric("SpO₂ (latest)", latest_spo2)
col5.metric("FiO₂ / Vent", f"{resp.get('fio2', '—')}% · {'Yes' if resp.get('mechanical_ventilation') else 'No'}")

diag = patient.diagnosis
st.caption(f"Data source: **{data_source}** · Diagnosis: {diag[:120]}{'…' if len(diag) > 120 else ''}")

tab_overview, tab_vitals, tab_labs, tab_clinical = st.tabs(
    ["Overview", "Vitals (time series)", "Labs & risk", "Clinical narrative"]
)

with tab_overview:
    if not patient.vitals:
        st.warning("No vitals available for this stay.")
    else:
        df_v = vitals_dataframe(patient.vitals)
        st.subheader("Vitals snapshot")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.line_chart(
                df_v.set_index("hour")[["heart_rate", "spo2", "resp_rate"]],
                height=320,
            )
        with c2:
            st.area_chart(
                df_v.set_index("hour")[["temperature"]],
                height=320,
            )
        st.dataframe(df_v, use_container_width=True, hide_index=True)

    if patient.labs:
        st.subheader("Laboratory panel")
        lab_df = pd.DataFrame(
            {"Analyte": list(patient.labs.keys()), "Value": list(patient.labs.values())}
        )
        st.bar_chart(lab_df.set_index("Analyte"), height=280)

with tab_vitals:
    if not patient.vitals:
        st.warning("No vitals available for this stay.")
    else:
        df_v = vitals_dataframe(patient.vitals)
        st.pyplot(plot_vitals_matplotlib(df_v), use_container_width=True)
        with st.expander("Raw vitals JSON"):
            st.json(patient.vitals)

with tab_labs:
    c_left, c_right = st.columns(2)
    with c_left:
        st.subheader("Laboratory results")
        if patient.labs:
            lab_df = pd.DataFrame(
                {"Analyte": list(patient.labs.keys()), "Value": list(patient.labs.values())}
            )
            fig_labs, ax = plt.subplots(figsize=(6, 4))
            colors = ["#2ecc71" if lab_within_screen(k, v) else "#e74c3c" for k, v in patient.labs.items()]
            ax.barh(lab_df["Analyte"], lab_df["Value"], color=colors)
            ax.set_xlabel("Value")
            ax.set_title("Lab panel (green = within typical ICU screen)")
            plt.tight_layout()
            st.pyplot(fig_labs, use_container_width=True)
        else:
            st.warning("No labs for this stay.")

    with c_right:
        st.subheader("Risk scores")
        if patient.risk_scores:
            risk_df = pd.DataFrame(
                {"Score": list(patient.risk_scores.keys()), "Value": list(patient.risk_scores.values())}
            )
            st.bar_chart(risk_df.set_index("Score"), height=300)
            st.json(patient.risk_scores)
        st.subheader("Respiratory support")
        st.json(patient.respiratory)
        st.subheader("Radiology / notes")
        st.json(patient.radiology)

with tab_clinical:
    st.subheader("Generated ICU summary")
    st.text(patient.narrative.strip())
