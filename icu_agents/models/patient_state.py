from pydantic import BaseModel, Field
from typing import Dict, List, Any


class PatientState(BaseModel):
    patient_id: str
    age: int
    gender: str
    diagnosis: str

    vitals: List[Dict[str, Any]] = Field(default_factory=list)
    labs: Dict[str, Any] = Field(default_factory=dict)
    radiology: Dict[str, Any] = Field(default_factory=dict)
    respiratory: Dict[str, Any] = Field(default_factory=dict)

    risk_scores: Dict[str, Any] = Field(default_factory=dict)
    narrative: str = ""
