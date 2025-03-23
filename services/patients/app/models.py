from werkzeug.security import generate_password_hash, check_password_hash

class Patient:
    def __init__(self, id=None, name=None, email=None, phoneNumber=None,  password=None):
        self.id = id  # Added ID field
        self.name = name
        self.email = email
        self.phoneNumber = phoneNumber  # Using camelCase
        self.password_hash = None
        if password:
            self.set_password(password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,  # Include ID
            'name': self.name,
            'email': self.email,
            'phoneNumber': self.phoneNumber,
            'password_hash': self.password_hash
        }

    @staticmethod
    def from_dict(data):
        patient = Patient(
            id=data.get('id'),  # Get ID from dictionary
            name=data.get('name'),
            email=data.get('email'),
            phoneNumber=data.get('phoneNumber'),  # Ensure camelCase
            date_of_birth=data.get('date_of_birth')  # Get date_of_birth
        )
        patient.password_hash = data.get('password_hash')  # Assign password_hash correctly
        return patient
