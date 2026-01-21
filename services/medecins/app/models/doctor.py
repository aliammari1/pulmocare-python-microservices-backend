from pydantic import BaseModel, EmailStr


class PydanticObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class DoctorBase(BaseModel):
    name: str
    email: EmailStr
    specialty: str
    phone: str
    address: str
    profile_picture: str | None = None
    is_verified: bool | None = False
    verification_details: dict | None = None
    signature: str | None = None
    bio: str | None = None
    license_number: str | None = None
    hospital: str | None = None
    education: str | None = None
    experience: str | None = None

    class Config:
        arbitrary_types_allowed = True


class DoctorCreate(DoctorBase):
    password: str


class DoctorUpdate(BaseModel):
    name: str | None = None
    specialty: str | None = None
    phone: str | None = None
    address: str | None = None
    profile_picture: str | None = None
    bio: str | None = None
    license_number: str | None = None
    hospital: str | None = None
    education: str | None = None
    experience: str | None = None

    class Config:
        arbitrary_types_allowed = True


class DoctorInDB(DoctorBase):
    id: str
    password_hash: bytes | None = None

    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class Doctor:
    def __init__(self, name, email, specialty, phone, address, password=None, _id=None):
        self._id = _id
        self.name = name
        self.email = email
        self.specialty = specialty
        self.phone = phone
        self.address = address
        # No longer storing password_hash - handled by Keycloak

    def to_dict(self):
        return {
            "id": self._id,
            "name": self.name,
            "email": self.email,
            "specialty": self.specialty,
            "phone": self.phone,
            "address": self.address,
            "profile_picture": getattr(self, "profile_picture", None),
            "is_verified": getattr(self, "is_verified", False),
            "verification_details": getattr(self, "verification_details", None),
            "signature": getattr(self, "signature", None),
            "bio": getattr(self, "bio", None),
            "licenseNumber": getattr(self, "license_number", None),
            "hospital": getattr(self, "hospital", None),
            "education": getattr(self, "education", None),
            "experience": getattr(self, "experience", None),
        }

    @classmethod
    def from_dict(cls, data):
        doctor = cls(
            name=data.get("name", ""),
            email=data.get("email", ""),
            specialty=data.get("specialty", ""),
            phone=data.get("phone", ""),
            address=data.get("address", ""),
        )
        doctor._id = data.get("id") or data.get("_id")
        if "profile_picture" in data:
            doctor.profile_picture = data["profile_picture"]
        if "is_verified" in data:
            doctor.is_verified = data["is_verified"]
        if "verification_details" in data:
            doctor.verification_details = data["verification_details"]
        if "signature" in data:
            doctor.signature = data["signature"]
        if "bio" in data:
            doctor.bio = data["bio"]
        if "licenseNumber" in data:
            doctor.license_number = data["licenseNumber"]
        if "hospital" in data:
            doctor.hospital = data["hospital"]
        if "education" in data:
            doctor.education = data["education"]
        if "experience" in data:
            doctor.experience = data["experience"]
        return doctor

    @classmethod
    def from_keycloak_data(cls, user_data):
        """Create a Doctor instance from Keycloak user data"""
        attributes = user_data.get("attributes", {})
        doctor = cls(
            _id=user_data.get("id"),
            name=f"{user_data.get('firstName', '')} {user_data.get('lastName', '')}".strip(),
            email=user_data.get("email", ""),
            specialty=(attributes.get("specialty", [""])[0] if isinstance(attributes.get("specialty", []), list) else attributes.get("specialty", "")),
            phone=(attributes.get("phone", [""])[0] if isinstance(attributes.get("phone", []), list) else attributes.get("phone", "")),
            address=(attributes.get("address", [""])[0] if isinstance(attributes.get("address", []), list) else attributes.get("address", "")),
        )

        # Add profile_picture if available
        if "profile_picture" in attributes:
            doctor.profile_picture = attributes["profile_picture"][0] if isinstance(attributes["profile_picture"], list) else attributes["profile_picture"]

        # Add verification status if available
        doctor.is_verified = attributes.get("is_verified", ["false"])[0] == "true" if isinstance(attributes.get("is_verified", []), list) else attributes.get("is_verified", "false") == "true"

        # Add verification details if available
        if "verification_details" in attributes:
            details_value = attributes["verification_details"]
            if isinstance(details_value, list) and details_value:
                doctor.verification_details = details_value[0]
            else:
                doctor.verification_details = details_value

        # Add signature if available
        if "signature" in attributes:
            doctor.signature = attributes["signature"][0] if isinstance(attributes["signature"], list) else attributes["signature"]

        # Add bio if available
        if "bio" in attributes:
            doctor.bio = attributes["bio"][0] if isinstance(attributes["bio"], list) else attributes["bio"]

        # Add license_number if available
        if "license_number" in attributes:
            doctor.license_number = attributes["license_number"][0] if isinstance(attributes["license_number"], list) else attributes["license_number"]

        # Add hospital if available
        if "hospital" in attributes:
            doctor.hospital = attributes["hospital"][0] if isinstance(attributes["hospital"], list) else attributes["hospital"]

        # Add education if available
        if "education" in attributes:
            doctor.education = attributes["education"][0] if isinstance(attributes["education"], list) else attributes["education"]

        # Add experience if available
        if "experience" in attributes:
            doctor.experience = attributes["experience"][0] if isinstance(attributes["experience"], list) else attributes["experience"]

        return doctor

    @classmethod
    def from_pydantic(cls, doctor_model: DoctorCreate):
        """Create a Doctor instance from a Pydantic model"""
        return cls(
            name=doctor_model.name,
            email=doctor_model.email,
            specialty=doctor_model.specialty,
            phone=doctor_model.phone,
            address=doctor_model.address,
        )

    def to_pydantic(self) -> DoctorInDB:
        """Convert to a Pydantic model"""
        return DoctorInDB(
            id=self._id,
            name=self.name,
            email=self.email,
            specialty=self.specialty,
            phone=self.phone,
            address=self.address,
            profile_picture=getattr(self, "profile_picture", None),
            is_verified=getattr(self, "is_verified", False),
            verification_details=getattr(self, "verification_details", None),
            signature=getattr(self, "signature", None),
            bio=getattr(self, "bio", None),
            license_number=getattr(self, "license_number", None),
            hospital=getattr(self, "hospital", None),
            education=getattr(self, "education", None),
            experience=getattr(self, "experience", None),
        )
