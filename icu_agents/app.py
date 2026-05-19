import argparse

from config import DATA_SOURCE
from data.eicu_loader import list_stay_ids
from orchestrator.patient_pipeline import PatientPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ICU multi-agent patient pipeline.")
    parser.add_argument(
        "--source",
        choices=["eicu", "synthetic"],
        default=DATA_SOURCE,
        help="Data source: eICU-CRD demo SQLite or synthetic generators.",
    )
    parser.add_argument(
        "--stay-id",
        type=int,
        default=None,
        help="eICU patientunitstayid (only used when --source eicu).",
    )
    args = parser.parse_args()

    pipeline = PatientPipeline()
    patient = pipeline.run(source=args.source, stay_id=args.stay_id)

    print(f"data_source={args.source}")
    if args.source == "eicu":
        print(f"eicu_stay_id={patient.patient_id}")
        print(f"available_stays_sample={list_stay_ids(5)}")

    print(patient.model_dump())
    print("\n\n===== ICU SUMMARY =====\n")
    print(patient.narrative)


if __name__ == "__main__":
    main()
