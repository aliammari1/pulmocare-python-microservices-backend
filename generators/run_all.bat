@echo off
echo Building generators...
cargo build --release

echo Running medecins_generator...
.\target\release\medecins_generator.exe -n 1000

echo Running patients_generator...
.\target\release\patients_generator.exe -n 1000

echo Running radiologues_generator...
.\target\release\radiologues_generator.exe -n 1000

echo Running ordonnances_generator...
.\target\release\ordonnances_generator.exe -n 1000

echo Running reports_generator...
.\target\release\reports_generator.exe -n 1000

echo All generators completed!
