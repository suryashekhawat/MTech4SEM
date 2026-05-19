"""Load ICU stays from the PhysioNet eICU-CRD demo SQLite bundle."""

from __future__ import annotations

import gzip
import os
import random
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.patient_state import PatientState

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EICU_DEMO_DIR = REPO_ROOT / "data" / "eicu-crd-demo"
SQLITE_GZ_NAME = "eicu_v2_0_1.sqlite3.gz"
SQLITE_NAME = "eicu_v2_0_1.sqlite3"

LAB_NAME_MAP = {
    "wbc x 1000": "WBC",
    "wbc": "WBC",
    "lactate": "Lactate",
    "creatinine": "Creatinine",
    "platelets x 1000": "Platelets",
    "platelets": "Platelets",
    "hgb": "Hemoglobin",
    "hemoglobin": "Hemoglobin",
}

DEFAULT_LABS = {
    "WBC": 0.0,
    "Lactate": 0.0,
    "Creatinine": 0.0,
    "Platelets": 0.0,
    "Hemoglobin": 0.0,
}


def eicu_demo_dir() -> Path:
    return Path(os.environ.get("EICU_DEMO_DIR", DEFAULT_EICU_DEMO_DIR))


def sqlite_path() -> Path:
    return eicu_demo_dir() / "sqlite" / SQLITE_NAME


def ensure_sqlite() -> Path:
    """Decompress the bundled SQLite file if only the .gz exists."""
    db_path = sqlite_path()
    gz_path = db_path.with_suffix(db_path.suffix + ".gz")

    if db_path.is_file():
        return db_path

    if not gz_path.is_file():
        raise FileNotFoundError(
            f"eICU SQLite not found at {db_path} or {gz_path}. "
            "Run scripts/download_eicu_crd_demo.py first."
        )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz_path, "rb") as src, db_path.open("wb") as dst:
        dst.write(src.read())
    return db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(ensure_sqlite())
    conn.row_factory = sqlite3.Row
    return conn


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_age(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    match = re.search(r"\d+", text)
    return int(match.group()) if match else 0


def list_stay_ids(limit: int = 500) -> List[int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT patientunitstayid FROM patient ORDER BY patientunitstayid LIMIT ?",
            (limit,),
        ).fetchall()
    return [int(row["patientunitstayid"]) for row in rows]


def sample_stay_id(seed: Optional[int] = None) -> int:
    stays = list_stay_ids()
    if not stays:
        raise RuntimeError("No patient stays found in eICU demo database.")
    rng = random.Random(seed)
    return rng.choice(stays)


def _is_usable_diagnosis(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 4:
        return False
    return cleaned.lower() not in {"no", "yes", "unknown", "n/a"}


def _load_diagnosis(conn: sqlite3.Connection, stay_id: int) -> str:
    row = conn.execute(
        "SELECT apacheadmissiondx FROM patient WHERE patientunitstayid = ?",
        (stay_id,),
    ).fetchone()
    if row and row["apacheadmissiondx"] and _is_usable_diagnosis(str(row["apacheadmissiondx"])):
        return str(row["apacheadmissiondx"])

    rows = conn.execute(
        """
        SELECT diagnosisstring
        FROM diagnosis
        WHERE patientunitstayid = ?
        ORDER BY diagnosispriority
        """,
        (stay_id,),
    ).fetchall()
    for row in rows:
        if row["diagnosisstring"] and _is_usable_diagnosis(str(row["diagnosisstring"])):
            return str(row["diagnosisstring"])

    rows = conn.execute(
        """
        SELECT admitdxtext
        FROM admissiondx
        WHERE patientunitstayid = ?
          AND admitdxtext IS NOT NULL
          AND admitdxtext != ''
        ORDER BY admissiondxid
        """,
        (stay_id,),
    ).fetchall()
    for row in rows:
        if _is_usable_diagnosis(str(row["admitdxtext"])):
            return str(row["admitdxtext"])

    return "ICU admission (eICU-CRD demo)"


def _load_vitals(conn: sqlite3.Connection, stay_id: int, max_hours: int = 24) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT observationoffset, heartrate, temperature, sao2, respiration, systemicsystolic
        FROM vitalperiodic
        WHERE patientunitstayid = ?
          AND heartrate IS NOT NULL
          AND heartrate != ''
        ORDER BY observationoffset
        """,
        (stay_id,),
    ).fetchall()

    if not rows:
        return []

    vitals: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if len(vitals) >= max_hours:
            break
        offset = int(row["observationoffset"] or 0)
        hour = max(0, offset // 60)
        vitals.append(
            {
                "timestamp": hour,
                "heart_rate": int(_safe_float(row["heartrate"], 0)),
                "temperature": round(_safe_float(row["temperature"], 98.6), 1),
                "spo2": int(_safe_float(row["sao2"], 97)),
                "resp_rate": int(_safe_float(row["respiration"], 18)),
                "systolic_bp": int(_safe_float(row["systemicsystolic"], 120)),
            }
        )

    if len(vitals) > max_hours:
        step = max(1, len(vitals) // max_hours)
        vitals = vitals[::step][:max_hours]

    return vitals


def _load_labs(conn: sqlite3.Connection, stay_id: int) -> Dict[str, float]:
    labs = dict(DEFAULT_LABS)
    rows = conn.execute(
        """
        SELECT labname, labresult, labresultoffset
        FROM lab
        WHERE patientunitstayid = ?
          AND labresult IS NOT NULL
          AND labresult != ''
        ORDER BY labresultoffset DESC
        """,
        (stay_id,),
    ).fetchall()

    for row in rows:
        key = LAB_NAME_MAP.get(str(row["labname"]).strip().lower())
        if key and labs.get(key, 0.0) == 0.0:
            labs[key] = round(_safe_float(row["labresult"]), 2)

    return labs


def _load_radiology(conn: sqlite3.Connection, stay_id: int) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT NOTETEXT, NOTETYPE
        FROM note
        WHERE patientunitstayid = ?
          AND NOTETEXT IS NOT NULL
          AND NOTETEXT != ''
        ORDER BY NOTEOFFSET DESC
        LIMIT 1
        """,
        (stay_id,),
    ).fetchone()
    if row:
        note_type = row["NOTETYPE"] or "clinical note"
        return {
            "report": f"{note_type}: {str(row['NOTETEXT'])[:500]}",
            "source": "eicu_note",
        }
    return {
        "report": "No imaging note available in eICU demo for this stay.",
        "source": "eicu_placeholder",
    }


def _load_respiratory(conn: sqlite3.Connection, stay_id: int) -> Dict[str, Any]:
    fio2 = 21
    peep = 5
    mechanical = False

    rows = conn.execute(
        """
        SELECT RESPCHARTVALUELABEL, RESPCHARTVALUE
        FROM respiratorycharting
        WHERE PATIENTUNITSTAYID = ?
        ORDER BY RESPCHARTOFFSET DESC
        LIMIT 50
        """,
        (stay_id,),
    ).fetchall()

    for row in rows:
        label = str(row["RESPCHARTVALUELABEL"] or "").lower()
        value = _safe_float(row["RESPCHARTVALUE"], 0)
        if "fio2" in label and value > 0:
            fio2 = int(min(100, value))
            mechanical = fio2 > 21
        if "peep" in label and value > 0:
            peep = int(value)

    if not rows:
        care = conn.execute(
            """
            SELECT VENTSTARTOFFSET, VENTENDOFFSET
            FROM respiratorycare
            WHERE PATIENTUNITSTAYID = ?
            LIMIT 1
            """,
            (stay_id,),
        ).fetchone()
        if care and care["VENTSTARTOFFSET"] not in (None, ""):
            mechanical = True
            fio2 = 40
            peep = 8

    return {
        "mechanical_ventilation": mechanical,
        "fio2": fio2,
        "peep": peep,
        "source": "eicu_respiratory",
    }


def load_patient_state(stay_id: int) -> PatientState:
    with _connect() as conn:
        row = conn.execute(
            "SELECT patientunitstayid, gender, age FROM patient WHERE patientunitstayid = ?",
            (stay_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"patientunitstayid {stay_id} not found in eICU demo.")

        diagnosis = _load_diagnosis(conn, stay_id)
        vitals = _load_vitals(conn, stay_id)
        labs = _load_labs(conn, stay_id)
        radiology = _load_radiology(conn, stay_id)
        respiratory = _load_respiratory(conn, stay_id)

    gender = str(row["gender"] or "Unknown")
    if gender.lower() in ("male", "m"):
        gender = "Male"
    elif gender.lower() in ("female", "f"):
        gender = "Female"

    return PatientState(
        patient_id=str(stay_id),
        age=_parse_age(row["age"]),
        gender=gender,
        diagnosis=diagnosis,
        vitals=vitals,
        labs=labs,
        radiology=radiology,
        respiratory=respiratory,
    )


def patient_state_to_dict(patient: PatientState, data_source: str = "eicu") -> Dict[str, Any]:
    payload = patient.model_dump()
    payload["data_source"] = data_source
    payload["eicu_stay_id"] = patient.patient_id
    return payload
