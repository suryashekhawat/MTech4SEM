import random


class LabAgent:
    def generate(self, diagnosis):
        wbc = 8
        lactate = 1.2
        creatinine = 0.9

        if diagnosis == "Sepsis":
            wbc = 18
            lactate = 4.5
            creatinine = 2.0

        if diagnosis == "ARDS":
            wbc = 14
            lactate = 2.5

        labs = {
            "WBC": round(random.normalvariate(wbc, 2), 1),
            "Lactate": round(random.normalvariate(lactate, 0.5), 1),
            "Creatinine": round(random.normalvariate(creatinine, 0.2), 1),
            "Platelets": random.randint(120, 300),
            "Hemoglobin": round(random.normalvariate(12.5, 1), 1),
        }

        return labs
