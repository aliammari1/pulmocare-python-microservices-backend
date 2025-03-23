import sys
import inspect

# Print the Python path to see where Python is looking for modules
print("Python path:", sys.path)

# Try to import the Patient class and inspect it
try:
    from models.patient import Patient
    print("Successfully imported Patient from models.patient")
    print("Patient __init__ parameters:", inspect.signature(Patient.__init__))
except Exception as e:
    print(f"Error importing from models.patient: {e}")

try:
    from models import Patient
    print("Successfully imported Patient directly from models")
    print("Patient __init__ parameters:", inspect.signature(Patient.__init__))
except Exception as e:
    print(f"Error importing directly from models: {e}")