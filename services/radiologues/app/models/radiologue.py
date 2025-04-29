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


class RadiologueBase(BaseModel):
    name: str
    email: EmailStr
    specialty: str
    phone: Optional[str] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            date: lambda d: d.isoformat() if d else None,
        }


class RadiologueCreate(RadiologueBase):
    password: str


class RadiologueUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class RadiologueInDB(RadiologueBase):
    id: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class Radiologue:
    def __init__(
        self,
        name,
        email,
        specialty,
        phone=None,
        address=None,
        password=None,
        _id=None,
    ):
        self._id = _id or ObjectId()
        self.name = name
        self.email = email
        self.specialty = specialty
        self.phone = phone
        self.address = address
        self.password_hash = None
        self.is_verified = False
        self.verification_details = None
        self.profile_picture = None
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
            "specialty": self.specialty,
            "phone": self.phone,
            "address": self.address,
            "profile_picture": getattr(self, "profile_picture", None),
            "is_verified": getattr(self, "is_verified", False),
            "verification_details": getattr(self, "verification_details", None),
            "created_at": getattr(self, "created_at", datetime.utcnow()),
        }

    @classmethod
    def from_dict(cls, data):
        radiologue = cls(
            name=data["name"],
            email=data["email"],
            specialty=data["specialty"],
            phone=data.get("phone"),
            address=data.get("address"),
        )
        radiologue._id = data["_id"]

        # Copy additional fields
        for field in ["profile_picture", "is_verified", "verification_details"]:
            if field in data:
                setattr(radiologue, field, data[field])

        if "created_at" in data:
            radiologue.created_at = data["created_at"]

        return radiologue

    @classmethod
    def from_pydantic(cls, radiologue_model: RadiologueCreate):
        """Create a Radiologue instance from a Pydantic model"""
        return cls(
            name=radiologue_model.name,
            email=radiologue_model.email,
            specialty=radiologue_model.specialty,
            phone=radiologue_model.phone,
            address=radiologue_model.address,
            password=radiologue_model.password,
        )

    def to_pydantic(self) -> RadiologueInDB:
        """Convert to a Pydantic model"""
        return RadiologueInDB(
            id=str(self._id),
            name=self.name,
            email=self.email,
            specialty=self.specialty,
            phone=self.phone,
            address=self.address,
            profile_picture=getattr(self, "profile_picture", None),
            is_verified=getattr(self, "is_verified", False),
            verification_details=getattr(self, "verification_details", None),
            created_at=getattr(self, "created_at", None),
        )
