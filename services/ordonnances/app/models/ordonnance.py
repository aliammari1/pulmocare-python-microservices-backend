from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel


class Medication(BaseModel):
    """Individual medication data"""

    name: str
    dosage: str
    frequency: str
    duration: str | None = None


class OrdonnanceBase(BaseModel):
    """Base model with common fields"""

    patient_id: str
    patient_name: str
    doctor_name: str
    medications: list[Medication]
    instructions: str
    diagnosis: str
    signature: str | None = None

    class Config:
        arbitrary_types_allowed = True


class OrdonnanceCreate(OrdonnanceBase):
    """Data needed to create a new prescription"""


class OrdonnanceUpdate(BaseModel):
    """Data that can be updated in a prescription"""

    patient_id: str | None = None
    patient_name: str | None = None
    doctor_name: str | None = None
    medications: list[Medication] | None = None
    instructions: str | None = None
    diagnosis: str | None = None
    signature: str | None = None

    class Config:
        arbitrary_types_allowed = True


class OrdonnanceInDB(OrdonnanceBase):
    """Model representing a prescription from the database"""

    id: str
    doctor_id: str
    date: datetime

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "_id": "60d21b4967d0d8992e610c85",
                "doctor_id": "60d21b4967d0d8992e610c80",
                "patient_id": "60d21b4967d0d8992e610c81",
                "patient_name": "John Doe",
                "doctor_name": "Dr. Jane Smith",
                "medications": [
                    {
                        "name": "Amoxicillin",
                        "dosage": "500mg",
                        "frequency": "3 times a day",
                        "duration": "7 days",
                    }
                ],
                "instructions": "Take with food. Complete the full course.",
                "diagnosis": "Bacterial infection",
                "date": "2023-04-20T14:30:00.000Z",
                "signature": "base64encoded_signature_data",
            }
        }


class OrdonnanceList(BaseModel):
    """List of prescriptions with pagination information"""

    items: list[OrdonnanceInDB]
    total: int
    page: int
    pages: int


class Ordonnance:
    """Class for handling ordonnance (prescription) documents"""

    def __init__(
        self,
        doctor_id: str,
        patient_id: str,
        patient_name: str,
        doctor_name: str,
        medications: list[dict],
        instructions: str,
        diagnosis: str,
        date: datetime = None,
        signature: str = None,
        _id: ObjectId = None,
    ):
        self._id = _id or ObjectId()
        self.doctor_id = doctor_id
        self.patient_id = patient_id
        self.patient_name = patient_name
        self.doctor_name = doctor_name
        self.medications = medications
        self.instructions = instructions
        self.diagnosis = diagnosis
        self.date = date or datetime.now()
        self.signature = signature

    @classmethod
    def from_dict(cls, data: dict):
        """Create an Ordonnance instance from a dictionary"""
        if not data:
            return None

        return cls(
            _id=data.get("_id"),
            doctor_id=data.get("doctor_id"),
            patient_id=data.get("patient_id"),
            patient_name=data.get("patient_name"),
            doctor_name=data.get("doctor_name"),
            medications=data.get("medications", []),
            instructions=data.get("instructions", ""),
            diagnosis=data.get("diagnosis", ""),
            date=data.get("date"),
            signature=data.get("signature"),
        )

    def to_dict(self) -> dict:
        """Convert Ordonnance to a dictionary for database storage"""
        return {
            "_id": self._id,
            "doctor_id": self.doctor_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "doctor_name": self.doctor_name,
            "medications": self.medications,
            "instructions": self.instructions,
            "diagnosis": self.diagnosis,
            "date": self.date,
            "signature": self.signature,
        }

    def to_pydantic(self) -> OrdonnanceInDB:
        """Convert to Pydantic model for API responses"""
        return OrdonnanceInDB(
            _id=str(self._id),
            doctor_id=self.doctor_id,
            patient_id=self.patient_id,
            patient_name=self.patient_name,
            doctor_name=self.doctor_name,
            medications=self.medications,
            instructions=self.instructions,
            diagnosis=self.diagnosis,
            date=self.date,
            signature=self.signature,
        )
