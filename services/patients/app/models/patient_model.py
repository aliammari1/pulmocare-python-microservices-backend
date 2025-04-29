from datetime import date, datetime
from typing import Any, Dict, Optional

import bcrypt
from bson import ObjectId
from pydantic import BaseModel, EmailStr


class PydanticObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(str(v)):
            raise ValueError("Invalid objectid")
        return ObjectId(str(v))

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class PatientBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    profile_picture: Optional[str] = None
    medical_history: Optional[Dict[str, Any]] = None
    insurance_details: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            date: lambda d: d.isoformat() if d else None,
        }


class PatientCreate(PatientBase):
    password: str


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    profile_picture: Optional[str] = None
    medical_history: Optional[Dict[str, Any]] = None
    insurance_details: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True


class PatientInDB(PatientBase):
    id: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    id: str
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    profile_picture: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class Patient:
    def __init__(
        self,
        name,
        email,
        phone=None,
        address=None,
        date_of_birth=None,
        password=None,
        _id=None,
    ):
        self._id = _id or ObjectId()
        self.name = name
        self.email = email
        self.phone = phone
        self.address = address
        self.date_of_birth = date_of_birth
        self.password_hash = None
        self.created_at = datetime.utcnow()
        if password:
            self.set_password(password)

    def set_password(self, password):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), salt)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash)

    def to_dict(self):
        return {
            "id": str(self._id),
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "date_of_birth": self.date_of_birth,
            "profile_picture": getattr(self, "profile_picture", None),
            "created_at": getattr(self, "created_at", datetime.utcnow()),
        }

    @classmethod
    def from_dict(cls, data):
        patient = cls(
            name=data["name"],
            email=data["email"],
            phone=data.get("phone"),
            address=data.get("address"),
            date_of_birth=data.get("date_of_birth"),
        )
        patient._id = data["_id"]

        # Copy additional fields
        for field in ["profile_picture", "medical_history", "insurance_details"]:
            if field in data:
                setattr(patient, field, data[field])

        if "created_at" in data:
            patient.created_at = data["created_at"]

        return patient

    @classmethod
    def from_pydantic(cls, patient_model: PatientCreate):
        """Create a Patient instance from a Pydantic model"""
        return cls(
            name=patient_model.name,
            email=patient_model.email,
            phone=patient_model.phone,
            address=patient_model.address,
            date_of_birth=patient_model.date_of_birth,
            password=patient_model.password,
        )

    def to_pydantic(self) -> PatientInDB:
        """Convert to a Pydantic model"""
        return PatientInDB(
            id=str(self._id),
            name=self.name,
            email=self.email,
            phone=self.phone,
            address=self.address,
            date_of_birth=self.date_of_birth,
            profile_picture=getattr(self, "profile_picture", None),
            medical_history=getattr(self, "medical_history", None),
            insurance_details=getattr(self, "insurance_details", None),
            created_at=getattr(self, "created_at", None),
        )
