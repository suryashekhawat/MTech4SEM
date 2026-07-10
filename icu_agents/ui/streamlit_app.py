import sys
from pathlib import Path

import os

import pandas as pd
import streamlit as st

# Ensure project root is importable regardless of launch directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(UI_ROOT) not in sys.path:
    sys.path.append(str(UI_ROOT))

from agents.clinical_chat_agent import ClinicalChatAgent
from agents.narrative_agent import NarrativeAgent
from clinical.critical_brief import build_critical_brief
from clinical.feedback_overlay import apply_doctor_feedback
from config import DATA_SOURCE
from data.eicu_loader import list_stay_ids
from data.temporal_timeline import build_timeline, patient_view_at_hour, snapshot_at_hour
from models.patient_state import PatientState
from orchestrator.patient_pipeline import PatientPipeline
from chart_helpers import (
    SCRUBBABLE_CHART_KEYS,
    build_events_timeline_figure,
    build_lab_events_figure,
    build_labs_bar_figure,
    build_overview_vitals_figure,
    build_risk_bar_figure,
    build_temperature_figure,
    build_vitals_figure,
    render_scrubbable_chart,
    render_static_chart,
    sync_hour_from_chart_selection,
    clear_chart_sync_tokens,
)

def chat_session_key(patient_id: str, hour: int) -> str:
    return f"doctor_chat_{patient_id}_{hour}"


def get_chat_history(patient_id: str, hour: int) -> list:
    key = chat_session_key(patient_id, hour)
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def append_chat_turn(patient_id: str, hour: int, role: str, content: str) -> None:
    history = get_chat_history(patient_id, hour)
    history.append({"role": role, "content": content})


def render_doctor_dialogue(
    patient: PatientState,
    snapshot: dict,
    selected_hour: int,
    pit_narrative: str,
    feedback_impact: dict = None,
    adjusted_brief: dict = None,
) -> None:
    st.divider()
    st.subheader("Doctor dialogue")
    st.caption(
        "Ask questions, challenge the assessment, or leave clinical feedback. "
        "Your input adjusts the Critical Patient Brief above — trajectory, alerts, and actions."
    )

    if feedback_impact:
        st.success(
            f"Your feedback adjusted the brief above: trajectory "
            f"**{feedback_impact.get('trajectory_before', '').upper()} → "
            f"{feedback_impact.get('trajectory_after', '').upper()}**, "
            f"{len(feedback_impact.get('actions_added', []))} new action(s).",
            icon="✅",
        )
    else:
        st.info(
            "No clinician dialogue yet at this hour. Use the chat below — e.g. "
            "“I disagree — patient is improving” — to see how the system response changes.",
            icon="💬",
        )

    if adjusted_brief and adjusted_brief.get("clinician_adjusted"):
        with st.expander("Revised SBAR after your feedback"):
            sbar = adjusted_brief.get("sbar", {})
            st.markdown(f"**Assessment:** {sbar.get('assessment', '')}")
            st.markdown(f"**Recommendation:** {sbar.get('recommendation', '')}")

    if os.environ.get("OPENAI_API_KEY"):
        st.success("LLM mode: OpenAI responses enabled.", icon="✅")
    else:
        st.info(
            "Rule-based mode: set `OPENAI_API_KEY` for richer conversational replies.",
            icon="ℹ️",
        )

    chat_agent = ClinicalChatAgent()
    history = get_chat_history(patient.patient_id, selected_hour)

    quick_col1, quick_col2, quick_col3 = st.columns(3)
    quick_prompts = {
        quick_col1: "Why is this severity level assigned?",
        quick_col2: "What are the recommended next steps?",
        quick_col3: "I disagree — the patient may be improving.",
    }
    for col, prompt in quick_prompts.items():
        if col.button(prompt, use_container_width=True):
            reply = chat_agent.respond(
                prompt,
                patient=patient_view_at_hour(patient, snapshot),
                snapshot=snapshot,
                hour=selected_hour,
                pit_narrative=pit_narrative,
                history=history,
            )
            append_chat_turn(patient.patient_id, selected_hour, "user", prompt)
            append_chat_turn(patient.patient_id, selected_hour, "assistant", reply)
            st.rerun()

    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if clear_col := st.columns([1, 5])[0]:
        if clear_col.button("Clear chat", key=f"clear_chat_{patient.patient_id}_{selected_hour}"):
            st.session_state[chat_session_key(patient.patient_id, selected_hour)] = []
            st.rerun()

    if user_input := st.chat_input("Ask a question or provide clinical feedback…"):
        view = patient_view_at_hour(patient, snapshot)
        history = get_chat_history(patient.patient_id, selected_hour)
        reply = chat_agent.respond(
            user_input,
            patient=view,
            snapshot=snapshot,
            hour=selected_hour,
            pit_narrative=pit_narrative,
            history=history,
        )
        append_chat_turn(patient.patient_id, selected_hour, "user", user_input)
        append_chat_turn(patient.patient_id, selected_hour, "assistant", reply)
        st.rerun()


SEVERITY_ICONS = {
    "stable": ":green-circle:",
    "worsening": ":orange-circle:",
    "critical": ":red-circle:",
}


def vitals_dataframe(vitals: list) -> pd.DataFrame:
    df = pd.DataFrame(vitals)
    if "hour" not in df.columns:
        if "timestamp" in df.columns:
            numeric_ts = pd.to_numeric(df["timestamp"], errors="coerce")
            if numeric_ts.notna().any():
                df["hour"] = numeric_ts
            else:
                df["hour"] = range(len(df))
        else:
            df["hour"] = range(len(df))
    else:
        df["hour"] = pd.to_numeric(df["hour"], errors="coerce")

    if "timestamp" in df.columns:
        df = df.drop(columns=["timestamp"])

    df = df.sort_values("hour").reset_index(drop=True)
    for col in ("heart_rate", "spo2", "resp_rate", "temperature", "systolic_bp"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def ensure_timeline(patient: PatientState, data_source: str) -> dict:
    timeline = st.session_state.get("timeline")
    if timeline is not None:
        return timeline

    timeline_stay = st.session_state.get("stay_id")
    if data_source == "eicu" and timeline_stay is None:
        try:
            timeline_stay = int(patient.patient_id)
        except ValueError:
            timeline_stay = None

    timeline = build_timeline(patient, source=data_source, stay_id=timeline_stay)
    st.session_state.timeline = timeline
    return timeline


def lab_within_screen(name: str, value: float) -> bool:
    checks = {
        "Lactate": value <= 4,
        "WBC": value <= 15,
        "Creatinine": value <= 2,
        "Platelets": value >= 100,
        "Hemoglobin": value >= 7,
    }
    return checks.get(name, True)


TRAJECTORY_ICONS = {
    "deteriorating": ":red_circle:",
    "improving": ":green_circle:",
    "stable": ":large_blue_circle:",
    "unknown": ":white_circle:",
}

ALERT_ICONS = {
    "critical": ":red_circle:",
    "warning": ":orange_circle:",
}


def _metric_delta(trend: dict):
    delta = trend.get("delta")
    if delta is None:
        return None
    unit = trend.get("unit", "")
    return f"{delta:+.1f}{unit} vs H{trend['prior_hour']}"


def _metric_delta_color(trend: dict) -> str:
    direction = trend.get("direction", "stable")
    label = trend.get("label", "")
    if direction == "stable":
        return "off"
    if label == "SpO₂":
        return "inverse" if direction == "worsening" else "normal"
    return "normal" if direction == "worsening" else "inverse"


def render_feedback_impact_panel(impact: dict) -> None:
    st.subheader("Clinician feedback impact on system response")
    st.caption(
        "Shows how doctor dialogue at this ICU hour adjusts trajectory, alerts, and recommended actions. "
        "Vitals and labs remain unchanged — only the clinical interpretation is updated."
    )

    c1, c2, c3, c4 = st.columns(4)
    traj_before = impact.get("trajectory_before", "—")
    traj_after = impact.get("trajectory_after", "—")
    c1.metric("Trajectory", traj_after.upper(), delta=f"was {traj_before}")
    c2.metric(
        "Active alerts",
        impact.get("alerts_after", 0),
        delta=f"{impact.get('alerts_after', 0) - impact.get('alerts_before', 0):+d} vs automated",
        delta_color="inverse",
    )
    c3.metric("Doctor turns", impact.get("doctor_turns", 0))
    c4.metric("Confidence", impact.get("confidence", "adjusted"))

    if traj_before != traj_after:
        st.info(
            f"Overall trajectory revised: **{traj_before.upper()} → {traj_after.upper()}** "
            f"based on clinician dialogue."
        )

    if impact.get("feedback_notes"):
        st.markdown("**What the clinician said (interpreted)**")
        for note in impact["feedback_notes"]:
            st.markdown(f"- {note}")

    if impact.get("alerts_overridden"):
        st.markdown("**Alerts downgraded / overridden**")
        for title in impact["alerts_overridden"]:
            st.markdown(f"- ~~{title}~~ — acknowledged by clinician")

    if impact.get("actions_added"):
        st.markdown("**New actions added from dialogue**")
        for action in impact["actions_added"]:
            st.markdown(f"- {action}")

    if impact.get("actions_removed"):
        st.markdown("**Actions deprioritized**")
        for action in impact["actions_removed"]:
            st.markdown(f"- {action}")

    st.divider()


def render_critical_brief_panel(brief: dict, title: str = "Critical Patient Brief") -> None:
    st.subheader(title)
    if brief.get("clinician_adjusted"):
        st.caption(f"Adjusted view · confidence: **{brief.get('feedback_confidence', 'clinician-adjusted')}**")
    trajectory = brief.get("trajectory", "unknown")
    st.markdown(
        f"**Overall trajectory:** {TRAJECTORY_ICONS.get(trajectory, '')} "
        f"**{trajectory.upper()}** · ICU hour **{brief['hour']}** · "
        f"6-hour lookback trends"
    )

    trend_map = {t["label"]: t for t in brief.get("trends", [])}
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    metric_cols = [
        (m1, "SpO₂"),
        (m2, "Heart rate"),
        (m3, "Lactate"),
        (m4, "Creatinine"),
        (m5, "FiO₂"),
    ]
    for col, label in metric_cols:
        trend = trend_map.get(label)
        if not trend:
            col.metric(label, "—")
            continue
        col.metric(
            f"{label} {trend['arrow']}",
            f"{trend['current']} {trend['unit']}",
            delta=_metric_delta(trend),
            delta_color=_metric_delta_color(trend),
        )
    alerts = brief.get("alerts", [])
    m6.metric("Active alerts", len(alerts))

    sbar = brief.get("sbar", {})
    left, right = st.columns(2)
    with left:
        st.markdown("**S — Situation**")
        st.write(sbar.get("situation", ""))
        st.markdown("**B — Background**")
        st.write(sbar.get("background", ""))
    with right:
        st.markdown("**A — Assessment**")
        st.write(sbar.get("assessment", ""))
        st.markdown("**R — Recommendation**")
        st.write(sbar.get("recommendation", ""))

    if alerts:
        st.markdown("**Active alerts (with evidence)**")
        for alert in alerts:
            icon = ALERT_ICONS.get(alert["level"], ":white_circle:")
            st.markdown(f"{icon} **{alert['title']}** — {alert['message']}  \n_Rule: {alert['rule']}_")
            if alert.get("evidence"):
                evidence_text = " · ".join(
                    f"H{item['hour']}: {item['text']}" for item in alert["evidence"]
                )
                st.caption(evidence_text)

    actions = brief.get("actions", [])
    if actions:
        st.markdown("**Recommended actions**")
        for action in actions:
            priority = action.get("priority", "medium").upper()
            source_tag = " · _clinician-directed_" if action.get("source") == "clinician" else ""
            st.markdown(
                f"- **[{priority}]** {action['action']} — _{action.get('detail', '')}_{source_tag}"
            )

    gaps = brief.get("data_gaps", [])
    if gaps:
        st.warning("Data gaps: " + " · ".join(gaps))

    st.divider()


st.set_page_config(page_title="ICU Pipeline", layout="wide")
st.title("ICU Multi-Agent Patient Pipeline")

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
        patient = pipeline.run(source=source, stay_id=stay_id)
        timeline_stay = stay_id
        if source == "eicu" and timeline_stay is None:
            timeline_stay = int(patient.patient_id)
        timeline = build_timeline(
            patient,
            source=source,
            stay_id=timeline_stay,
        )
        st.session_state.patient = patient
        st.session_state.data_source = source
        st.session_state.stay_id = stay_id
        st.session_state.timeline = timeline
        st.session_state.pit_hour_slider = int(timeline["hours"][-1])
        clear_chart_sync_tokens()

if "patient" not in st.session_state:
    st.info("Select options in the sidebar and click **Run ICU Pipeline** to load data and charts.")
    st.stop()

patient: PatientState = st.session_state.patient
data_source = st.session_state.get("data_source", source)
timeline = ensure_timeline(patient, data_source)

if not timeline.get("vitals"):
    st.warning("No vitals timeline available for this stay.")
    st.stop()

hours = timeline["hours"]
if "pit_hour_slider" not in st.session_state:
    st.session_state.pit_hour_slider = int(hours[-1])

for chart_key in SCRUBBABLE_CHART_KEYS:
    sync_hour_from_chart_selection(chart_key, hours)

jump_col1, jump_col2, jump_col3, jump_col4 = st.columns(4)
if jump_col1.button("Jump to admission (H0)", use_container_width=True):
    clear_chart_sync_tokens()
    st.session_state.pit_hour_slider = int(hours[0])
    st.rerun()
if jump_col2.button(f"Jump to mid-stay (H{hours[len(hours) // 2]})", use_container_width=True):
    clear_chart_sync_tokens()
    st.session_state.pit_hour_slider = int(hours[len(hours) // 2])
    st.rerun()
if jump_col3.button(f"Jump to latest (H{hours[-1]})", use_container_width=True):
    clear_chart_sync_tokens()
    st.session_state.pit_hour_slider = int(hours[-1])
    st.rerun()
jump_col4.caption("Click chart points to scrub · dashed line = selected hour")

selected_hour = st.slider(
    "ICU hour (offset from admission)",
    min_value=int(hours[0]),
    max_value=int(hours[-1]),
    step=1,
    key="pit_hour_slider",
    help="Scrub time here or click any point on a vitals/events chart.",
    on_change=clear_chart_sync_tokens,
)

snapshot = snapshot_at_hour(patient, timeline, selected_hour)
view = patient_view_at_hour(patient, snapshot)
pit_narrative = NarrativeAgent().generate(
    view,
    hour=selected_hour,
    recent_events=snapshot["events"],
)

row = snapshot["vitals_row"]
labs = snapshot["labs"]
resp = snapshot["respiratory"]
risk = snapshot["risk_scores"]
severity = snapshot["severity"]

critical_brief = build_critical_brief(patient, snapshot, timeline, selected_hour)
chat_history = get_chat_history(patient.patient_id, selected_hour)
adjusted_brief, feedback_impact = apply_doctor_feedback(critical_brief, chat_history, snapshot)

if feedback_impact:
    render_feedback_impact_panel(feedback_impact)
    render_critical_brief_panel(adjusted_brief, title="Critical Patient Brief (clinician-adjusted)")
    with st.expander("View automated baseline (before clinician feedback)"):
        render_critical_brief_panel(critical_brief, title="Automated baseline")
else:
    render_critical_brief_panel(critical_brief)

diag = patient.diagnosis
st.caption(
    f"**Stay {patient.patient_id}** · **{patient.age}y {patient.gender}** · "
    f"Data source: **{data_source}** · "
    f"Diagnosis: {diag[:120]}{'…' if len(diag) > 120 else ''} · "
    f"Severity **{severity.upper()}** {SEVERITY_ICONS[severity]} · "
    f"Mortality risk (heuristic) **{risk.get('mortality_risk', 0)}%** · "
    f"FiO₂ **{resp.get('fio2', '—')}%** · Vent **{'Yes' if resp.get('mechanical_ventilation') else 'No'}**"
)

tab_overview, tab_vitals, tab_labs, tab_clinical, tab_dialogue = st.tabs(
    [
        "Overview",
        "Vitals (time series)",
        "Labs & risk",
        "Clinical narrative",
        "Doctor dialogue",
    ]
)

vitals_upto_hour = view.vitals
df_v = vitals_dataframe(vitals_upto_hour) if vitals_upto_hour else pd.DataFrame()

with tab_overview:
    st.subheader(f"Overview at ICU hour {selected_hour}")
    if df_v.empty:
        st.warning("No vitals available up to this hour.")
    else:
        st.markdown(
            f"**Severity:** {SEVERITY_ICONS[severity]} **{severity.upper()}** · "
            f"HR {row.get('heart_rate', '—')} bpm · SpO₂ {row.get('spo2', '—')}% · "
            f"Lactate {labs.get('Lactate', '—')}"
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            render_scrubbable_chart(
                build_overview_vitals_figure(df_v, selected_hour),
                "overview_vitals_chart",
            )
        with c2:
            render_scrubbable_chart(
                build_temperature_figure(df_v, selected_hour),
                "overview_temp_chart",
            )
        st.dataframe(df_v, use_container_width=True, hide_index=True)

    if labs:
        st.subheader(f"Laboratory panel known at hour {selected_hour}")
        render_static_chart(
            build_labs_bar_figure(labs, selected_hour, lab_within_screen),
            "overview_labs_bar_chart",
        )

    render_scrubbable_chart(
        build_events_timeline_figure(snapshot["events"], selected_hour),
        "overview_events_chart",
    )

with tab_vitals:
    st.subheader(f"Vitals through ICU hour {selected_hour}")
    if df_v.empty:
        st.warning("No vitals available up to this hour.")
    else:
        render_scrubbable_chart(
            build_vitals_figure(df_v, selected_hour),
            "vitals_detail_chart",
        )
        st.caption(
            f"Current vitals at hour {selected_hour}: HR {row.get('heart_rate')} bpm, "
            f"SpO₂ {row.get('spo2')}%, RR {row.get('resp_rate')}/min, "
            f"Temp {row.get('temperature')}°F, SBP {row.get('systolic_bp', '—')}"
        )
        with st.expander("Vitals history JSON (hours 0–selected)"):
            st.json(vitals_upto_hour)

with tab_labs:
    st.subheader(f"Laboratory & risk at ICU hour {selected_hour}")
    render_scrubbable_chart(
        build_lab_events_figure(timeline.get("lab_events", []), selected_hour),
        "lab_events_chart",
    )
    c_left, c_right = st.columns(2)
    with c_left:
        st.subheader("Laboratory results")
        if labs:
            render_static_chart(
                build_labs_bar_figure(labs, selected_hour, lab_within_screen),
                "labs_tab_bar_chart",
            )
        else:
            st.warning("No labs recorded yet at this hour.")

    with c_right:
        st.subheader("Risk scores")
        if risk:
            render_static_chart(build_risk_bar_figure(risk, selected_hour), "labs_tab_risk_chart")
            st.json(risk)
        st.subheader("Respiratory support")
        st.json(resp)
        st.subheader("Radiology / notes")
        st.json(snapshot["radiology"])

with tab_clinical:
    st.subheader(f"Clinical report at ICU hour {selected_hour}")
    st.text(pit_narrative.strip())

    render_scrubbable_chart(
        build_events_timeline_figure(snapshot["events"], selected_hour),
        "clinical_events_chart",
    )

with tab_dialogue:
    st.subheader(f"Doctor dialogue at ICU hour {selected_hour}")
    render_doctor_dialogue(
        patient=view,
        snapshot=snapshot,
        selected_hour=selected_hour,
        pit_narrative=pit_narrative,
        feedback_impact=feedback_impact,
        adjusted_brief=adjusted_brief,
    )
