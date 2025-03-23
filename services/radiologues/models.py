import bcrypt
from bson import ObjectId


#Doctor
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
        # Generate a salt and hash the password
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
    
    
# Classe Report pour gérer l'entité
class Rapport:
    def __init__(self, patient_name, exam_type, report_type, content, date=None):
        self.patient_name = patient_name
        self.exam_type = exam_type
        self.report_type = report_type
        self.content = content
        self.date = date if date else datetime.datetime.utcnow()

    def to_dict(self):
        return {
            "patient_name": self.patient_name,
            "exam_type": self.exam_type,
            "report_type": self.report_type,
            "content": self.content,
            "date": self.date
        }

    def save(self):
        mongo.db.rapports.insert_one(self.to_dict())
