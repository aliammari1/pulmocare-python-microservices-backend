from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash


class Patient:
    def __init__(
        self,
        id=None,
        name=None,
        email=None,
        phoneNumber=None,
        password=None,
        date_of_birth=None,
        medical_history=None,
    ):
        self.id = id
        self.name = name
        self.email = email
        self.phoneNumber = phoneNumber
        self.date_of_birth = date_of_birth
        self.medical_history = medical_history or []
        self.password_hash = None
        if password:
            self.set_password(password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phoneNumber": self.phoneNumber,
            "date_of_birth": self.date_of_birth,
            "medical_history": self.medical_history,
            "password_hash": self.password_hash,
        }

    @staticmethod
    def from_dict(data):
        return Patient(
            id=data.get("id"),
            name=data.get("name"),
            email=data.get("email"),
            phoneNumber=data.get("phoneNumber"),
            date_of_birth=data.get("date_of_birth"),
            medical_history=data.get("medical_history", []),
            password=None,  # Don't set password, instead set hash directly
        )._set_password_hash(data.get("password_hash"))

    def _set_password_hash(self, hash_value):
        self.password_hash = hash_value
        return self
