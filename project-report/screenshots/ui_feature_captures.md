# ICU Streamlit Dashboard — Feature Screenshots

Captured from `http://localhost:8501` using Playwright (eICU stay **141764**, ICU hour **5**).

---

## 01 — Pipeline setup (`01_pipeline_setup.png`)

**Feature:** Sidebar configuration and pipeline trigger.

The left sidebar lets the operator choose the **data source** (`eicu` or `synthetic`), select an **eICU patientunitstayid** from the demo SQLite database, and click **Run ICU Pipeline** to load vitals, labs, notes, and respiratory data through the multi-agent `PatientPipeline`. The main panel shows the landing prompt until a run completes.

---

## 02 — Critical Patient Brief (`02_critical_patient_brief.png`)

**Feature:** Automated SBAR-style critical-care summary.

After the pipeline runs, the dashboard displays a **Critical Patient Brief** with overall trajectory (STABLE / IMPROVING / DETERIORATING), six-hour trend deltas for SpO₂, heart rate, lactate, creatinine, and FiO₂, active alert count, SBAR sections (Situation, Background, Assessment, Recommendation), prioritized recommended actions, and data-gap warnings. This panel is the primary decision-support view for the selected ICU hour.

---

## 03 — ICU hour scrubber (`03_icu_hour_scrubber.png`)

**Feature:** Point-in-time temporal navigation.

Clinicians scrub the ICU stay using **Jump to admission / mid-stay / latest** buttons, an **ICU hour slider** (offset from admission), or by clicking points on interactive Plotly charts. A dashed vertical line marks the selected hour across charts. All tabs and the Critical Patient Brief refresh to show only data known up to that hour—preventing future-data leakage.

---

## 04 — Overview tab (`04_tab_overview.png`)

**Feature:** Consolidated bedside snapshot at the selected hour.

The **Overview** tab combines severity and current vitals summary, multi-series vitals charts (heart rate, SpO₂, respiratory rate), temperature trend, a tabular vitals history, laboratory bar chart with in-range/out-of-range colouring, and a clinical events timeline (admission, vitals, notes). It gives a single-screen picture of patient status at the scrubbed hour.

---

## 05 — Vitals (time series) tab (`05_tab_vitals.png`)

**Feature:** Detailed vital-sign time series.

The **Vitals** tab renders a full multi-axis Plotly chart of heart rate, SpO₂, respiratory rate, temperature, and systolic BP through the selected ICU hour, with the current-hour marker. A caption lists vitals at the selected hour; an expander exposes raw JSON for audit or debugging.

---

## 06 — Labs & risk tab (`06_tab_labs_risk.png`)

**Feature:** Laboratory results, risk scores, and respiratory metadata.

The **Labs & risk** tab shows lab draw events over time, a bar chart of the latest known lab panel (WBC, lactate, creatinine, platelets, hemoglobin), heuristic **mortality / sepsis / deterioration** risk scores, respiratory support JSON (FiO₂, PEEP, mechanical ventilation), and radiology/notes metadata available at the selected hour.

---

## 07 — Clinical narrative tab (`07_tab_clinical_narrative.png`)

**Feature:** Point-in-time narrative generation.

The **Clinical narrative** tab displays the output of `NarrativeAgent` for the scrubbed hour—a human-readable ICU report incorporating demographics, severity, latest vitals/labs, and recent clinical events. An events timeline chart below the text anchors the narrative in time.

---

## 08 — Doctor dialogue tab (`08_tab_doctor_dialogue.png`)

**Feature:** Clinician chat and quick prompts.

The **Doctor dialogue** tab supports conversational interaction via `ClinicalChatAgent`. Quick-action buttons ask about severity rationale, recommended next steps, or express clinical disagreement. Chat history persists per patient and hour; responses use OpenAI when `OPENAI_API_KEY` is set, otherwise rule-based fallback. Clinician input feeds the feedback overlay that adjusts the Critical Patient Brief above.

---

## 09 — Clinician feedback overlay (`09_clinician_feedback_overlay.png`)

**Feature:** Human-in-the-loop brief adjustment.

After the clinician selects *"I disagree — the patient may be improving"*, the **Clinician feedback impact** panel shows before/after trajectory (e.g., STABLE → IMPROVING), alert count changes, doctor turn count, and interpreted feedback notes. The brief is re-rendered as **Critical Patient Brief (clinician-adjusted)** with updated assessment, recommendations, and clinician-directed actions. An expander preserves the automated baseline for comparison. Underlying vitals and labs remain unchanged.
