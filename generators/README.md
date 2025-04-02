# MedApp Database Generators

This project contains high-performance database generators for the MedApp application. Each generator creates realistic test data for different entities in the system.

## Features

- Written in Rust for maximum performance
- Progress bars for visual feedback
- Batch processing for efficient database operations
- Comprehensive logging
- CLI interfaces for all generators

## Prerequisites

1. [Install Rust](https://www.rust-lang.org/tools/install) (1.60+ recommended)
2. MongoDB running on localhost:27017 with admin:admin credentials

## Building

```bash
cargo build --release
```

## Usage

Each generator can be run separately:

```bash
# Generate 10 doctors
./target/release/medecins_generator -n 10

# Generate 50 patients
./target/release/patients_generator -n 50

# Generate 5 radiologists
./target/release/radiologues_generator -n 5

# Generate 20 prescriptions
./target/release/ordonnances_generator -n 20

# Generate 30 reports
./target/release/reports_generator -n 30
```

You can also run all generators with default values using the provided scripts:

- On Linux/macOS: `./run_all.sh`
- On Windows: `run_all.bat`

## Command-line Options

All generators support the following options:

- `-n, --number <COUNT>`: Number of records to generate (default varies by generator)
- `-v, --verbose`: Enable verbose logging

## Generator Order

For proper data relationships, run the generators in this order:

1. `medecins_generator` (doctors)
2. `patients_generator` (patients)
3. `radiologues_generator` (radiologists)
4. `ordonnances_generator` (prescriptions)
5. `reports_generator` (reports)

The last two generators require that doctors, patients, and radiologists already exist in the database.

## Performance

The Rust implementation is significantly faster than the Python version, especially for large datasets. Examples:

- 1,000 doctors: ~1 second (compared to ~10 seconds in Python)
- 10,000 patients: ~5 seconds (compared to ~90 seconds in Python)

## Notes

- All password fields are hashed with bcrypt using the default value "password"
- For very large datasets, adjust your MongoDB configuration accordingly
