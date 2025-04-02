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
    nom: String,
    dosage: String,
    frequence: String,
    duree: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct Ordonnance {
    medecin_id: ObjectId,
    patient_id: ObjectId,
    dateCreation: String,
    medicaments: Vec<Medication>,
    instructions: String,
    renouvellements: i32,
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
        "Doliprane",
        "Advil",
        "Smecta",
        "Amoxicilline",
        "Spasfon",
        "Levothyrox",
        "Dafalgan",
        "Imodium",
        "Ventoline",
        "Augmentin",
        "Voltarene",
        "Plavix",
        "Kardegic",
        "Tahor",
        "Xanax",
    ];

    Medication {
        nom: medications.choose(&mut rng).unwrap().to_string(),
        dosage: format!("{} mg", rng.gen_range(100..1001)),
        frequence: format!("{} fois par jour", rng.gen_range(1..4)),
        duree: format!("{} jours", rng.gen_range(3..15)),
    }
}

// Generate a random prescription using cached IDs
fn generate_ordonnance(medecin_ids: &[ObjectId], patient_ids: &[ObjectId]) -> Ordonnance {
    let mut rng = thread_rng();

    let now = Utc::now();
    let one_year_ago = now - Duration::days(365);
    let random_days = rng.gen_range(0..(now - one_year_ago).num_days());
    let date_creation = (one_year_ago + Duration::days(random_days)).to_rfc3339();

    let num_medicaments = rng.gen_range(1..6);
    let medicaments = (0..num_medicaments)
        .map(|_| generate_medication())
        .collect();

    Ordonnance {
        medecin_id: medecin_ids.choose(&mut rng).unwrap().clone(),
        patient_id: patient_ids.choose(&mut rng).unwrap().clone(),
        dateCreation: date_creation,
        medicaments,
        instructions: Paragraph(1..3).fake(),
        renouvellements: rng.gen_range(0..4),
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
                "medecin_id": ordonnance.medecin_id,
                "patient_id": ordonnance.patient_id,
                "dateCreation": ordonnance.dateCreation,
                "medicaments": ordonnance.medicaments
                    .iter()
                    .map(|med| doc! {
                        "nom": &med.nom,
                        "dosage": &med.dosage,
                        "frequence": &med.frequence,
                        "duree": &med.duree,
                    })
                    .collect::<Vec<Document>>(),
                "instructions": ordonnance.instructions,
                "renouvellements": ordonnance.renouvellements,
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
