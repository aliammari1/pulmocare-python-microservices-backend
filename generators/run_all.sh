#!/bin/bash

# Build the Rust project
echo "Building generators..."
cargo build --release

# Run each generator with default values
echo "Running medecins_generator..."
./target/release/medecins_generator -n 1000

echo "Running patients_generator..."
./target/release/patients_generator -n 1000

echo "Running radiologues_generator..."
./target/release/radiologues_generator -n 1000

echo "Running ordonnances_generator..."
./target/release/ordonnances_generator -n 1000

echo "Running reports_generator..."
./target/release/reports_generator -n 1000

echo "All generators completed!"
