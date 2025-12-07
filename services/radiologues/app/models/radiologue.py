from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, EmailStr


class PydanticObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v


class RadiologueBase(BaseModel):
    name: str
    email: EmailStr
    specialty: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    license_number: Optional[str] = None
    hospital: Optional[str] = None


class RadiologueCreate(RadiologueBase):
    password: str


class RadiologueUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    specialty: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    license_number: Optional[str] = None
    hospital: Optional[str] = None
    is_verified: Optional[bool] = None
    verification_details: Optional[Dict] = None


class RadiologueInDB(RadiologueBase):
    id: PydanticObjectId
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict] = None
    created_at: Optional[datetime] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class Radiologue:
    def __init__(
            self,
            name,
            email,
            specialty=None,
            phone=None,
            address=None,
            license_number=None,
            hospital=None,
            _id=None,
    ):
        self._id = _id
        self.name = name
        self.email = email
        self.specialty = specialty
        self.phone = phone
        self.address = address
        self.license_number = license_number
        self.hospital = hospital
        self.created_at = datetime.utcnow()
        self.is_verified = False
        self.verification_details = None

    @classmethod
    def from_keycloak_data(cls, user_data):
        """Create a Radiologue instance from Keycloak user data"""
        attributes = user_data.get("attributes", {})

        # Get name from Keycloak data
        name = user_data.get("name", "")
        if not name and ("firstName" in user_data or "lastName" in user_data):
            first_name = user_data.get("firstName", "")
            last_name = user_data.get("lastName", "")
            name = f"{first_name} {last_name}".strip()

        # Create radiologue instance
        radiologue = cls(
            _id=user_data.get("id"),
            name=name,
            email=user_data.get("email", ""),
            specialty=(
                attributes.get("specialty", [""])[0]
                if isinstance(attributes.get("specialty", []), list)
                   and attributes.get("specialty", [])
                else attributes.get("specialty", "")
            ),
            phone=(
                attributes.get("phone", [""])[0]
                if isinstance(attributes.get("phone", []), list)
                   and attributes.get("phone", [])
                else attributes.get("phone", "")
            ),
            address=(
                attributes.get("address", [""])[0]
                if isinstance(attributes.get("address", []), list)
                   and attributes.get("address", [])
                else attributes.get("address", "")
            ),
            license_number=(
                attributes.get("license_number", [""])[0]
                if isinstance(attributes.get("license_number", []), list)
                   and attributes.get("license_number", [])
                else attributes.get("license_number", "")
            ),
            hospital=(
                attributes.get("hospital", [""])[0]
                if isinstance(attributes.get("hospital", []), list)
                   and attributes.get("hospital", [])
                else attributes.get("hospital", "")
            ),
        )

        # Add is_verified if available
        is_verified = attributes.get("is_verified")
        if is_verified:
            radiologue.is_verified = (
                str(is_verified[0]).lower() == "true"
                if isinstance(is_verified, list) and is_verified
                else str(is_verified).lower() == "true"
            )

        # Add verification_details if available
        verification_details = attributes.get("verification_details")
        if verification_details:
            try:
                if isinstance(verification_details, list) and verification_details:
                    radiologue.verification_details = verification_details[0]
                else:
                    radiologue.verification_details = verification_details
            except (ValueError, TypeError):
                pass

        # Convert created_at from string if available
        created_at = attributes.get("created_at")
        if created_at:
            try:
                created_at_value = (
                    created_at[0]
                    if isinstance(created_at, list) and created_at
                    else created_at
                )
                radiologue.created_at = datetime.fromisoformat(created_at_value)
            except (ValueError, TypeError):
                radiologue.created_at = datetime.utcnow()

        return radiologue

    def to_dict(self):
        """Convert Radiologue to dictionary"""
        return {
            "id": self._id,
            "name": self.name,
            "email": self.email,
            "specialty": self.specialty,
            "phone": self.phone,
            "address": self.address,
            "license_number": self.license_number,
            "hospital": self.hospital,
            "is_verified": getattr(self, "is_verified", False),
            "verification_details": getattr(self, "verification_details", None),
            "created_at": getattr(self, "created_at", datetime.utcnow()),
        }

    def to_pydantic(self):
        """Convert to Pydantic model"""
        radiologue_dict = self.to_dict()
        radiologue_dict["id"] = radiologue_dict.pop("_id", None) or radiologue_dict.get(
            "id"
        )
        return RadiologueInDB(**radiologue_dict)
