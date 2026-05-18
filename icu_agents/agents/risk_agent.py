class RiskAgent:
    def calculate(self, vitals, labs):
        score = 0

        latest = vitals[-1]

        if latest["spo2"] < 90:
            score += 20

        if latest["heart_rate"] > 120:
            score += 15

        if labs["Lactate"] > 4:
            score += 25

        if labs["Creatinine"] > 2:
            score += 15

        mortality_risk = min(score, 100)

        return {
            "mortality_risk": mortality_risk,
            "sepsis_risk": mortality_risk * 0.8,
            "icu_deterioration_risk": mortality_risk * 0.9,
        }
