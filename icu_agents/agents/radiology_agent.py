class RadiologyAgent:
    def generate(self, diagnosis):
        findings = {
            "Sepsis": "Chest X-ray shows bilateral infiltrates concerning for infectious process.",
            "ARDS": "Diffuse bilateral pulmonary opacities consistent with ARDS.",
            "Pneumonia": "Right lower lobe consolidation suspicious for pneumonia.",
            "Aortic Dissection": "CT angiography demonstrates Type A aortic dissection.",
            "COPD Exacerbation": "Hyperinflation noted without focal consolidation.",
            "Heart Failure": "Pulmonary vascular congestion and mild edema present.",
        }

        return {"report": findings.get(diagnosis)}
