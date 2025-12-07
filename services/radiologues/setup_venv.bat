@echo off
echo Setting up virtual environment for radiologues service...

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists.
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo Virtual environment setup complete for radiologues service.
echo To activate the virtual environment, run: venv\Scripts\activate.bat