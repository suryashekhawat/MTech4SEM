from orchestrator.patient_pipeline import PatientPipeline


pipeline = PatientPipeline()
patient = pipeline.run()

print(patient.model_dump())

print("\n\n===== ICU SUMMARY =====\n")
print(patient.narrative)
