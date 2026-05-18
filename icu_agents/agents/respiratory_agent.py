import random


class RespiratoryAgent:
    def generate(self, diagnosis):
        ventilation = False
        fio2 = 21
        peep = 5

        if diagnosis in ["ARDS", "Sepsis"]:
            ventilation = True
            fio2 = random.randint(50, 90)
            peep = random.randint(8, 14)

        return {
            "mechanical_ventilation": ventilation,
            "fio2": fio2,
            "peep": peep,
        }
