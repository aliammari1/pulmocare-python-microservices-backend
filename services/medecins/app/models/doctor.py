from typing import Dict, Optional

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


class DoctorBase(BaseModel):
    name: str
    email: EmailStr
    specialty: str
    phone_number: str
    address: str
    profile_image: Optional[str] = None
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict] = None
    signature: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
        }


class DoctorCreate(DoctorBase):
    password: str


class DoctorUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    profile_image: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class DoctorInDB(DoctorBase):
    id: str
    password_hash: Optional[bytes] = None

    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class Doctor:
    def __init__(
        self, name, email, specialty, phone_number, address, password=None, _id=None
    ):
        self._id = _id or ObjectId()
        self.name = name
        self.email = email
        self.specialty = specialty
        self.phone_number = phone_number
        self.address = address
        self.password_hash = None
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
            "specialty": self.specialty,
            "phone_number": self.phone_number,
            "address": self.address,
            "profile_image": (
                self.profile_image if hasattr(self, "profile_image") else None
            ),
        }

    @classmethod
    def from_dict(cls, data):
        doctor = cls(
            name=data["name"],
            email=data["email"],
            specialty=data["specialty"],
            phone_number=data["phone_number"],
            address=data["address"],
        )
        doctor._id = data["_id"]
        if "profile_image" in data:
            doctor.profile_image = data["profile_image"]
        return doctor

    @classmethod
    def from_pydantic(cls, doctor_model: DoctorCreate):
        """Create a Doctor instance from a Pydantic model"""
        return cls(
            name=doctor_model.name,
            email=doctor_model.email,
            specialty=doctor_model.specialty,
            phone_number=doctor_model.phone_number,
            address=doctor_model.address,
            password=doctor_model.password,
        )

    def to_pydantic(self) -> DoctorInDB:
        """Convert to a Pydantic model"""
        return DoctorInDB(
            id=str(self._id),
            name=self.name,
            email=self.email,
            specialty=self.specialty,
            phone_number=self.phone_number,
            address=self.address,
            profile_image=getattr(self, "profile_image", None),
            is_verified=getattr(self, "is_verified", False),
            verification_details=getattr(self, "verification_details", None),
            signature=getattr(self, "signature", None),
            password_hash=self.password_hash,
        )
