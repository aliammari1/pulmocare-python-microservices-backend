import bcrypt
from bson import ObjectId

class Doctor:
    def __init__(self, name, email, specialty, phone_number, address, password=None, _id=None):
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
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash)

    def to_dict(self):
        return {
            'id': str(self._id),
            'name': self.name,
            'email': self.email,
            'specialty': self.specialty,
            'phone_number': self.phone_number,
            'address': self.address,
            'profile_image': self.profile_image if hasattr(self, 'profile_image') else None
        }

    @classmethod
    def from_dict(cls, data):
        doctor = cls(
            name=data['name'],
            email=data['email'],
            specialty=data['specialty'],
            phone_number=data['phone_number'],
            address=data['address']
        )
        doctor._id = data['_id']
        if 'profile_image' in data:
            doctor.profile_image = data['profile_image']
        return doctor
