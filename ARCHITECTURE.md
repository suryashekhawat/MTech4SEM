# ICU Pipeline — System Architecture

> Setup and commands: [README.md](README.md)

Mermaid diagrams for the current **ICU-pipeline** setup: PhysioNet [eICU-CRD demo v2.0.1](https://physionet.org/content/eicu-crd-demo/2.0.1/), `icu_agents` multi-agent stack, and Apache Airflow orchestration.

---

## 1. High-level overview

```mermaid
flowchart TB
    subgraph External["External data"]
        PN["PhysioNet eICU-CRD demo v2.0.1"]
        DL["scripts/download_eicu_crd_demo.py"]
    end

    subgraph DataLocal["Local data (git-ignored)"]
        DEMO["data/eicu-crd-demo/"]
        SQL["sqlite/eicu_v2_0_1.sqlite3"]
        CSV["*.csv.gz tables"]
        DEMO --> SQL
        DEMO --> CSV
    end

    subgraph Repo["ICU-pipeline repository"]
        subgraph AgentsPkg["icu_agents/"]
            CFG["config.py"]
            LOAD["data/eicu_loader.py"]
            PIPE["data/pipeline_source.py"]
            ORCH["orchestrator/patient_pipeline.py"]
            STATE["models/patient_state.py"]
            AGENTS["agents/*.py"]
            SYN["synthetic/clinical_rules.py"]
            OUT["output/ json | reports | timelines"]
        end

        subgraph Entry["Entry points"]
            CLI["app.py"]
            UI["ui/streamlit_app.py"]
        end

        subgraph AirflowStack["Airflow (Docker)"]
            DC["docker-compose.yml"]
            DAG1["icu_multi_agent_pipeline"]
            DAG2["icu_temporal_reasoning_pipeline"]
        end

        REPORT["project-report/main.tex → main.pdf"]
    end

    PN --> DL
    DL --> DEMO
    SQL --> LOAD
    LOAD --> PIPE
    SYN --> PIPE
    AGENTS --> PIPE
    PIPE --> ORCH
    ORCH --> STATE
    CFG --> LOAD
    CFG --> PIPE

    CLI --> ORCH
    UI --> ORCH
    PIPE --> DAG1
    PIPE --> DAG2
    DAG1 --> OUT
    DAG2 --> OUT

    DC --> DAG1
    DC --> DAG2
    DEMO -.->|volume mount| DC
```

---

## 2. Data source modes (`ICU_DATA_SOURCE`)

```mermaid
flowchart LR
    subgraph Config
        SRC{"ICU_DATA_SOURCE<br/>eicu | synthetic"}
    end

    subgraph EICU["eicu (default)"]
        E1["eicu_loader.ensure_sqlite()"]
        E2["Query patientunitstayid"]
        E3["Map vitalperiodic → vitals[]"]
        E4["Map lab → WBC, Lactate, …"]
        E5["Map note / respiratorycharting"]
        E1 --> E2 --> E3 --> E4 --> E5
    end

    subgraph Synthetic["synthetic"]
        S1["clinical_rules.generate_base_patient()"]
        S2["VitalsAgent / LabAgent / …"]
        S1 --> S2
    end

    subgraph Shared["Shared processing"]
        R["RiskAgent.calculate()"]
        N["NarrativeAgent.generate()"]
        PS["PatientState"]
    end

    subgraph Fallback["Hybrid fallback"]
        F["Sparse eICU fields → synthetic agents"]
    end

    SRC -->|eicu| EICU
    SRC -->|synthetic| Synthetic
    E5 --> F
    F --> R
    E5 --> R
    S2 --> R
    R --> N --> PS
```

---

## 3. Agent layer and `PatientState`

```mermaid
flowchart TB
    PS["PatientState (Pydantic)"]

    PS --- ID["patient_id / eicu_stay_id"]
    PS --- DEMO["age, gender, diagnosis"]
    PS --- V["vitals[] hourly trace"]
    PS --- L["labs: WBC, Lactate, Creatinine, …"]
    PS --- RAD["radiology.report"]
    PS --- RESP["respiratory: FiO2, PEEP, vent"]
    PS --- RISK["risk_scores"]
    PS --- NAR["narrative"]

    subgraph Loaders["Data loaders"]
        EL["eicu_loader.load_patient_state()"]
        CR["clinical_rules + VitalsAgent …"]
    end

    subgraph Reasoning["Rule-based agents"]
        RA["RiskAgent"]
        NA["NarrativeAgent"]
    end

    subgraph OptionalSynth["Synthetic-only / fallback"]
        VA["VitalsAgent"]
        LA["LabAgent"]
        RDA["RadiologyAgent"]
        REA["RespiratoryAgent"]
    end

    EL --> PS
    CR --> PS
    EL -.->|gaps| VA & LA & RDA & REA
    V --> RA
    L --> RA
    RA --> NA
    PS --> NA
```

---

## 4. Local execution paths

```mermaid
sequenceDiagram
    actor User
    participant CLI as app.py
    participant ST as streamlit_app.py
    participant PP as PatientPipeline
    participant PS as pipeline_source
    participant EL as eicu_loader
    participant DB as eicu_v2_0_1.sqlite3
    participant Agents as RiskAgent + NarrativeAgent

    User->>CLI: python app.py --source eicu --stay-id N
    User->>ST: Select stay + Run Pipeline

    CLI->>PP: run(source, stay_id)
    ST->>PP: run(source, stay_id)

    PP->>PS: build_patient_state()
    PS->>EL: load_patient_state(stay_id)
    EL->>DB: SQL queries
    DB-->>EL: vitals, labs, notes, …
    EL-->>PS: PatientState (partial)
    PS->>Agents: risk + narrative
    Agents-->>PP: complete PatientState
    PP-->>User: JSON + ICU summary
```

---

## 5. Airflow: `icu_multi_agent_pipeline`

```mermaid
flowchart LR
    subgraph Docker["Docker Compose"]
        PG[(PostgreSQL)]
        WS[Airflow Webserver :8080]
        SCH[Airflow Scheduler]
        VOL["Volume: icu_agents/"]
        DATA["Volume: data/eicu-crd-demo/"]
    end

    subgraph DAG["icu_multi_agent_pipeline @daily"]
        T1["load_patient_from_source<br/>build_patient_dict()"]
        T2["store_patient_bundle"]
        T3["update_dashboard"]
        T1 --> T2 --> T3
    end

    subgraph Artifacts["icu_agents/output/"]
        J["json/{patient_id}.json"]
        R["reports/{patient_id}.txt"]
        D["timelines/latest_dashboard.json"]
    end

    SCH --> DAG
    DATA --> T1
    VOL --> T1
    T2 --> J & R
    T3 --> D
```

---

## 6. Airflow: `icu_temporal_reasoning_pipeline`

```mermaid
flowchart TB
    START["load_temporal_bundle<br/>(eICU vitals + labs)"]

    TRACE["build_hourly_reasoning_trace<br/>stable | worsening | critical"]

    START --> TRACE

    TRACE --> BH{"branch_hypoxia<br/>SpO2 < 85?"}
    TRACE --> BS{"branch_septic_shock<br/>Lactate > 4?"}

    BH -->|yes| RH["trigger_respiratory_escalation"]
    BH -->|no| SH["skip_respiratory_escalation"]

    BS -->|yes| SS["trigger_sepsis_escalation"]
    BS -->|no| SK["skip_sepsis_escalation"]

    RH --> COORD["coordinator_agent<br/>FiO2/PEEP + sepsis actions"]
    SH --> COORD
    SS --> COORD
    SK --> COORD

    COORD --> LG["optional_langgraph_handoff<br/>(placeholder)"]
    LG --> TN["generate_temporal_narrative"]
    TN --> STORE["store_temporal_outputs"]

    subgraph Out["output/"]
        TR["timelines/{id}_temporal_trace.json"]
        RP["reports/{id}_temporal_report.txt"]
    end

    STORE --> TR & RP
```

---

## 7. Repository layout

```mermaid
flowchart LR
    ROOT["ICU-pipeline/"]

    ROOT --> DATA["data/eicu-crd-demo/<br/>(gitignored)"]
    ROOT --> SCRIPTS["scripts/<br/>download_eicu_crd_demo.*"]
    ROOT --> AGENTS["icu_agents/"]
    ROOT --> REPORT["project-report/<br/>main.tex, main.pdf"]
    ROOT --> ARCH["ARCHITECTURE.md"]

    AGENTS --> A1["agents/"]
    AGENTS --> A2["data/eicu_loader.py"]
    AGENTS --> A3["data/pipeline_source.py"]
    AGENTS --> A4["orchestrator/"]
    AGENTS --> A5["airflow/dags/"]
    AGENTS --> A6["ui/streamlit_app.py"]
    AGENTS --> A7["output/"]
```

---

## 8. Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ICU_DATA_SOURCE` | `eicu` | `eicu` or `synthetic` |
| `EICU_DEMO_DIR` | `data/eicu-crd-demo` | Path to PhysioNet demo files |
| `OPENAI_MODEL` | `gpt-4o-mini` | Reserved for future LLM narrative |

---

## Quick commands

```bash
# Download dataset (background)
bash scripts/download_eicu_crd_demo.sh

# Local pipeline (eICU stay)
cd icu_agents && python app.py --source eicu --stay-id 147784

# Streamlit UI
cd icu_agents && streamlit run ui/streamlit_app.py

# Airflow
cd icu_agents && docker compose up -d
# UI: http://localhost:8080
```
