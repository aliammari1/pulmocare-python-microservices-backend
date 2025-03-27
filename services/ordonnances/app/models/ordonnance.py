class Ordonnance:
    def __init__(
        self,
        patient_id,
        medecin_id,
        medicaments,
        date=None,
        clinique=None,
        specialite=None,
    ):
        self.patient_id = str(patient_id)
        self.medecin_id = str(medecin_id)
        self.medicaments = medicaments
        self.date = date
        self.clinique = str(clinique or "")
        self.specialite = str(specialite or "")

    def to_dict(self):
        return {
            "patient_id": self.patient_id,
            "medecin_id": self.medecin_id,
            "medicaments": [
                {
                    "name": med.get("name", ""),
                    "dosage": med.get("dosage", ""),
                    "posologie": med.get("posologie", ""),
                    "laboratoire": med.get("laboratoire", ""),
                }
                for med in self.medicaments
            ],
            "date": self.date,
            "clinique": self.clinique,
            "specialite": self.specialite,
        }

    @staticmethod
    def from_dict(data):
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        required_fields = ["patient_id", "medecin_id", "medicaments"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        return Ordonnance(
            patient_id=data["patient_id"],
            medecin_id=data["medecin_id"],
            medicaments=data["medicaments"],
            date=data.get("date"),
            clinique=data.get("clinique", ""),
            specialite=data.get("specialite", ""),
        )
