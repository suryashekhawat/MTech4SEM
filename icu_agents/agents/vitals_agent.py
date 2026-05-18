import random
from datetime import datetime, timedelta


class VitalsAgent:
    def generate(self, diagnosis, hours=24):
        vitals = []

        base_hr = 82
        base_temp = 98.6
        base_spo2 = 97

        if diagnosis == "Sepsis":
            base_hr = 118
            base_temp = 101.5
            base_spo2 = 92

        if diagnosis == "ARDS":
            base_spo2 = 85
            base_hr = 110

        now = datetime.now()

        for h in range(hours):
            row = {
                "timestamp": str(now + timedelta(hours=h)),
                "heart_rate": round(random.normalvariate(base_hr, 6), 1),
                "temperature": round(random.normalvariate(base_temp, 0.6), 1),
                "spo2": round(random.normalvariate(base_spo2, 2), 1),
                "resp_rate": round(random.normalvariate(22, 3), 1),
                "systolic_bp": round(random.normalvariate(110, 12), 1),
            }

            vitals.append(row)

        return vitals
