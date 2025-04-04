use chrono::{Duration, Utc};
use clap::Parser;
use fake::faker::lorem::en::Paragraph;
use fake::{Fake, Faker};
use futures::StreamExt;
use indicatif::{ProgressBar, ProgressStyle};
use log::{debug, error, info};
use medapp_generators::{connect_to_mongodb, setup_logger};
use mongodb::bson::{doc, oid::ObjectId, Document};
use rand::{seq::SliceRandom, thread_rng, Rng};
use serde::{Deserialize, Serialize};
use std::error::Error;

#[derive(Debug, Serialize, Deserialize)]
struct Medication {
    name: String,
    dosage: String,
    frequency: String,
    duration: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct Ordonnance {
    doctor_id: ObjectId,
    patient_id: ObjectId,
    patient_name: String,
    doctor_name: String,
    medications: Vec<Medication>,
    instructions: String,
    diagnosis: String,
    date: String,
    signature: Option<String>,
}

#[derive(Parser, Debug)]
#[clap(author, version, about = "Generate random prescriptions")]
struct Args {
    #[clap(short, long, default_value_t = 20)]
    number: usize,

    #[clap(short, long)]
    verbose: bool,
}

// Cache IDs from the database to avoid repeated queries
async fn cache_ids(
    db: &mongodb::Database,
) -> Result<(Vec<ObjectId>, Vec<ObjectId>), Box<dyn Error>> {
    info!("Caching doctor and patient IDs");

    let medecins_collection = db.collection::<Document>("doctors");
    let patients_collection = db.collection::<Document>("patients");

    // Fix cursor handling to properly process MongoDB results
    let mut medecin_cursor = medecins_collection.find(None, None).await?;
    let mut medecin_ids = Vec::new();
    while let Some(result) = medecin_cursor.next().await {
        let document = result?;
        medecin_ids.push(document.get_object_id("_id").unwrap().clone());
    }

    let mut patient_cursor = patients_collection.find(None, None).await?;
    let mut patient_ids = Vec::new();
    while let Some(result) = patient_cursor.next().await {
        let document = result?;
        patient_ids.push(document.get_object_id("_id").unwrap().clone());
    }

    if medecin_ids.is_empty() || patient_ids.is_empty() {
        return Err(
            "No doctors or patients found in the database. Please generate them first.".into(),
        );
    }

    info!(
        "Cached {} doctor IDs and {} patient IDs",
        medecin_ids.len(),
        patient_ids.len()
    );

    Ok((medecin_ids, patient_ids))
}

// Generate a random medication
fn generate_medication() -> Medication {
    let mut rng = thread_rng();

    let medications = vec![
        "Amoxicillin", "Ibuprofen", "Paracetamol", "Aspirin", 
        "Loratadine", "Omeprazole", "Metformin", "Lisinopril",
        "Atorvastatin", "Albuterol", "Levothyroxine", "Metoprolol",
        "Prednisone", "Gabapentin", "Amlodipine"
    ];

    Medication {
        name: medications.choose(&mut rng).unwrap().to_string(),
        dosage: format!("{} mg", rng.gen_range(100..1001)),
        frequency: format!("{} times per day", rng.gen_range(1..4)),
        duration: Some(format!("{} days", rng.gen_range(3..15))),
    }
}

// Generate a random prescription using cached IDs
fn generate_ordonnance(medecin_ids: &[ObjectId], patient_ids: &[ObjectId]) -> Ordonnance {
    let mut rng = thread_rng();

    let now = Utc::now();
    let one_year_ago = now - Duration::days(365);
    let random_days = rng.gen_range(0..(now - one_year_ago).num_days());
    let date_creation = (one_year_ago + Duration::days(random_days)).to_rfc3339();

    let common_diagnoses = vec![
        "Upper respiratory infection", 
        "Hypertension", 
        "Type 2 diabetes", 
        "Acute bronchitis", 
        "Allergic rhinitis",
        "Urinary tract infection",
        "Viral gastroenteritis",
        "Migraine headache",
        "Anxiety disorder",
        "Lower back pain"
    ];

    let first_names = vec!["John", "Jane", "Michael", "Sarah", "David", "Lisa", "Robert", "Emily", "William", "Olivia"];
    let last_names = vec!["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Garcia", "Rodriguez", "Wilson"];
    let doctor_titles = vec!["Dr.", "Dr.", "Prof.", "Dr.", "Dr."];
    
    let patient_first_name = first_names.choose(&mut rng).unwrap();
    let patient_last_name = last_names.choose(&mut rng).unwrap();
    let patient_name = format!("{} {}", patient_first_name, patient_last_name);
    
    let doctor_first_name = first_names.choose(&mut rng).unwrap();
    let doctor_last_name = last_names.choose(&mut rng).unwrap();
    let doctor_title = doctor_titles.choose(&mut rng).unwrap();
    let doctor_name = format!("{} {} {}", doctor_title, doctor_first_name, doctor_last_name);

    let num_medications = rng.gen_range(1..4);
    let medications = (0..num_medications)
        .map(|_| generate_medication())
        .collect();

    Ordonnance {
        doctor_id: medecin_ids.choose(&mut rng).unwrap().clone(),
        patient_id: patient_ids.choose(&mut rng).unwrap().clone(),
        patient_name,
        doctor_name,
        medications,
        instructions: Paragraph(1..2).fake(),
        diagnosis: common_diagnoses.choose(&mut rng).unwrap().to_string(),
        date: date_creation,
        signature: if rng.gen_bool(0.7) {
            Some("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABg".to_string())
        } else {
            None
        },
    }
}

async fn generate_ordonnances(count: usize) -> Result<(), Box<dyn Error>> {
    let (db, client) = connect_to_mongodb().await?;
    let collection = db.collection::<Document>("ordonnances");

    // Cache IDs for better performance
    let (medecin_ids, patient_ids) = cache_ids(&db).await?;

    info!("Starting generation of {} prescriptions", count);

    let pb = ProgressBar::new(count as u64);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} prescriptions generated ({eta})")
        .unwrap()
        .progress_chars("#>-"));

    // Process in batches of 100 for better performance
    let batch_size = 100;
    let num_batches = (count + batch_size - 1) / batch_size;

    for batch_idx in 0..num_batches {
        let mut batch = Vec::with_capacity(batch_size);
        let current_batch_size = std::cmp::min(batch_size, count - batch_idx * batch_size);

        for _ in 0..current_batch_size {
            let ordonnance = generate_ordonnance(&medecin_ids, &patient_ids);

            batch.push(doc! {
                "doctor_id": ordonnance.doctor_id,
                "patient_id": ordonnance.patient_id,
                "patient_name": ordonnance.patient_name,
                "doctor_name": ordonnance.doctor_name,
                "date": ordonnance.date,
                "medications": ordonnance.medications
                    .iter()
                    .map(|med| doc! {
                        "name": &med.name,
                        "dosage": &med.dosage,
                        "frequency": &med.frequency,
                        "duration": &med.duration,
                    })
                    .collect::<Vec<Document>>(),
                "instructions": ordonnance.instructions,
                "diagnosis": ordonnance.diagnosis,
                "signature": ordonnance.signature,
            });
        }

        // Insert batch
        match collection.insert_many(batch, None).await {
            Ok(result) => {
                debug!(
                    "Inserted batch {}/{} with {} prescriptions",
                    batch_idx + 1,
                    num_batches,
                    result.inserted_ids.len()
                );
                pb.inc(current_batch_size as u64);
            }
            Err(e) => {
                error!("Failed to insert batch: {}", e);
                return Err(Box::new(e));
            }
        }
    }

    pb.finish_with_message("All prescriptions generated successfully");
    info!("Successfully added {} prescriptions to the database", count);

    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    setup_logger(args.verbose);

    if args.number <= 0 {
        error!("Number of prescriptions must be greater than 0");
        return Err("Number of prescriptions must be greater than 0".into());
    }

    generate_ordonnances(args.number).await?;

    Ok(())
}
