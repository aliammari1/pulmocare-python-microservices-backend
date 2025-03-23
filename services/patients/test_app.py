# backend/test_app.py


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

        # Clear the patients collection before each test
        patients_collection.delete_many({})

    def test_register(self):
        response = self.app.post('/register', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 201)
        self.assertIn('Patient registered successfully', response.get_data(as_text=True))

        # Test registering the same patient again
        response = self.app.post('/register', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Patient already exists', response.get_data(as_text=True))

    def test_login(self):
        # Register a patient first
        self.app.post('/register', json={
            'email': 'test@example.com',
            'password': 'password123'
        })

        # Test login with correct credentials
        response = self.app.post('/login', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.get_json())

        # Test login with incorrect credentials
        response = self.app.post('/login', json={
            'email': 'test@example.com',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn('Invalid credentials', response.get_data(as_text=True))

        # Test login with non-existent patient
        response = self.app.post('/login', json={
            'email': 'nonexistent@example.com',