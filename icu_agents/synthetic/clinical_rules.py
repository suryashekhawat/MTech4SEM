import random

DIAGNOSES = [
    "Sepsis",
    "ARDS",
    "Pneumonia",
    "Aortic Dissection",
    "COPD Exacerbation",
    "Heart Failure",
]

GENDERS = ["Male", "Female"]


def generate_base_patient():
    diagnosis = random.choice(DIAGNOSES)

    return {
        "age": random.randint(24, 88),
        "gender": random.choice(GENDERS),
        "diagnosis": diagnosis,
    }
