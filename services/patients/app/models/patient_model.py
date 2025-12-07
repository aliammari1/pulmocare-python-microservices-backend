from datetime import date, datetime
from typing import List, Optional, Annotated

from pydantic import BaseModel, EmailStr, BeforeValidator, PlainSerializer


# Update PydanticObjectId to be compatible with Pydantic v2
class PydanticObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        """
        Return a schema that will validate strings as object IDs
        and convert non-strings to strings
        """
        from pydantic_core import PydanticCustomError, core_schema

        def validate_object_id(value):
            if not isinstance(value, str):
                return str(value)
            return value

        return core_schema.string_schema(
            serialization=core_schema.plain_serializer_function_ser_schema(str),
            json_schema_extra={
                "type": "string",
                "format": "objectid",
            },
        )


# Define a reusable type
ObjectIdAnnotated = Annotated[
    str,
    BeforeValidator(lambda v: str(v) if not isinstance(v, str) else v),
    PlainSerializer(lambda v: str(v)),
]


class PatientBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    blood_type: Optional[str] = None
    social_security_number: Optional[str] = None
    medical_history: Optional[List[str]] = []
    allergies: Optional[List[str]] = []
    height: Optional[float] = None
    weight: Optional[float] = None
    medical_files: Optional[List[str]] = []


class PatientCreate(PatientBase):
    password: str


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    blood_type: Optional[str] = None
    social_security_number: Optional[str] = None
    medical_history: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    medical_files: Optional[List[str]] = None


class PatientInDB(PatientBase):
    id: ObjectIdAnnotated
    created_at: Optional[datetime] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user_id: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    user_id: str
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
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
            _id=None,
    ):
        self._id = _id
        self.name = name
        self.email = email
        self.phone = phone
        self.address = address
        self.date_of_birth = date_of_birth
        self.created_at = datetime.utcnow()
        self.blood_type = None
        self.social_security_number = None
        self.medical_history = []
        self.allergies = []
        self.height = None
        self.weight = None
        self.medical_files = []

    @classmethod
    def from_keycloak_data(cls, user_data):
        """Create a Patient instance from Keycloak user data"""
        attributes = user_data.get("attributes", {})

        # Get name from Keycloak data
        name = user_data.get("name", "")
        if not name and ("firstName" in user_data or "lastName" in user_data):
            first_name = user_data.get("firstName", "")
            last_name = user_data.get("lastName", "")
            name = f"{first_name} {last_name}".strip()

        # Create patient instance
        patient = cls(
            _id=user_data.get("id"),
            name=name,
            email=user_data.get("email", ""),
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
            date_of_birth=(
                attributes.get("date_of_birth", [""])[0]
                if isinstance(attributes.get("date_of_birth", []), list)
                   and attributes.get("date_of_birth", [])
                else attributes.get("date_of_birth", "")
            ),
        )

        # Add blood_type if available
        blood_type = attributes.get("blood_type")
        if blood_type:
            patient.blood_type = (
                blood_type[0]
                if isinstance(blood_type, list) and blood_type
                else blood_type
            )

        # Add social_security_number if available
        ssn = attributes.get("social_security_number")
        if ssn:
            patient.social_security_number = (
                ssn[0] if isinstance(ssn, list) and ssn else ssn
            )

        # Add medical_history if available
        medical_history = attributes.get("medical_history")
        if medical_history:
            patient.medical_history = (
                medical_history
                if isinstance(medical_history, list)
                else [medical_history]
            )

        # Add allergies if available
        allergies = attributes.get("allergies")
        if allergies:
            patient.allergies = (
                allergies if isinstance(allergies, list) else [allergies]
            )

        # Add height if available
        height = attributes.get("height")
        if height:
            try:
                height_value = (
                    height[0] if isinstance(height, list) and height else height
                )
                patient.height = float(height_value)
            except (ValueError, TypeError):
                pass

        # Add weight if available
        weight = attributes.get("weight")
        if weight:
            try:
                weight_value = (
                    weight[0] if isinstance(weight, list) and weight else weight
                )
                patient.weight = float(weight_value)
            except (ValueError, TypeError):
                pass

        # Add medical_files if available
        medical_files = attributes.get("medical_files")
        if medical_files:
            patient.medical_files = (
                medical_files if isinstance(medical_files, list) else [medical_files]
            )

        # Convert created_at from string if available
        created_at = attributes.get("created_at")
        if created_at:
            try:
                created_at_value = (
                    created_at[0]
                    if isinstance(created_at, list) and created_at
                    else created_at
                )
                patient.created_at = datetime.fromisoformat(created_at_value)
            except (ValueError, TypeError):
                patient.created_at = datetime.utcnow()

        return patient

    def to_dict(self):
        """Convert Patient to dictionary"""
        return {
            "id": self._id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "date_of_birth": self.date_of_birth,
            "blood_type": getattr(self, "blood_type", None),
            "social_security_number": getattr(self, "social_security_number", None),
            "medical_history": getattr(self, "medical_history", []),
            "allergies": getattr(self, "allergies", []),
            "height": getattr(self, "height", None),
            "weight": getattr(self, "weight", None),
            "medical_files": getattr(self, "medical_files", []),
            "created_at": getattr(self, "created_at", datetime.utcnow()),
        }

    def to_pydantic(self):
        """Convert to Pydantic model"""
        patient_dict = self.to_dict()
        patient_dict["id"] = patient_dict.pop("_id", None) or patient_dict.get("id")
        return PatientInDB(**patient_dict)
