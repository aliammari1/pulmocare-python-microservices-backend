use clap::Parser;
use fake::faker::address::en::StreetName;
use fake::faker::internet::en::FreeEmail;
use fake::faker::lorem::en::{Sentence, Word};
use fake::faker::name::en::{FirstName, LastName};
use fake::faker::phone_number::en::PhoneNumber;
use fake::{Fake, faker};
use fake::faker::name::raw::*;
use fake::faker::internet::raw::*;
use fake::faker::phone_number::raw::*;
use fake::faker::address::raw::*;
use fake::faker::lorem::raw::*;
use futures::StreamExt;
use log::{info, debug, error};
use medapp_generators::{connect_to_mongodb, setup_logger, hash_password};
use mongodb::bson::{Document, doc};
use rand::{thread_rng, Rng, seq::SliceRandom};
use serde::{Deserialize, Serialize};
use std::error::Error;
use tokio::task;
use indicatif::{ProgressBar, ProgressStyle};
use chrono::{Utc, Duration, NaiveDate};

#[derive(Debug, Serialize, Deserialize)]
struct Patient {
    nom: String,
    prenom: String,
    email: String,
    telephone: String,
    adresse: String,
    dateNaissance: String,
    groupeSanguin: String,
    numeroSecuriteSociale: String,
    antecedentsMedicaux: Vec<String>,
    allergies: Vec<String>,
    dateInscription: String,
    password: String,
}

#[derive(Parser, Debug)]
#[clap(author, version, about = "Generate random patients")]
struct Args {
    #[clap(short, long, default_value_t = 50)]
    number: usize,
    
    #[clap(short, long)]
    verbose: bool,
}

async fn generate_patients(count: usize) -> Result<(), Box<dyn Error>> {
    let (db, _client) = connect_to_mongodb().await?;
    let collection = db.collection::<Document>("patients");
    
    let blood_types = vec!["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
    
    info!("Starting generation of {} patients", count);
    
    let pb = ProgressBar::new(count as u64);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} patients generated ({eta})")
        .unwrap()
        .progress_chars("#>-"));
    
    // Process in batches of 100 for better performance
    let batch_size = 100;
    let num_batches = (count + batch_size - 1) / batch_size;
    
    for batch_idx in 0..num_batches {
        let mut batch = Vec::with_capacity(batch_size);
        let current_batch_size = std::cmp::min(batch_size, count - batch_idx * batch_size);
        
        for _ in 0..current_batch_size {
            let mut rng = thread_rng();
            
            let now = Utc::now();
            let two_years_ago = now - Duration::days(365 * 2);
            let random_days = rng.gen_range(0..(now - two_years_ago).num_days());
            let date_inscription = (two_years_ago + Duration::days(random_days)).to_rfc3339();
            
            // Generate a birth date between 1 and 90 years ago
            let years_ago = rng.gen_range(1..91);
            let birth_date = (now - Duration::days(365 * years_ago)).date_naive();
            
            let nom = LastName().fake::<String>();
            let prenom = FirstName().fake::<String>();
            let email = FreeEmail().fake::<String>();
            
            let numero_securite_sociale = (0..15).map(|_| rng.gen_range(0..10).to_string()).collect::<String>();
            
            let antecedents: Vec<String> = if rng.gen_bool(0.3) {
                (0..rng.gen_range(1..4)).map(|_| Sentence(3..10).fake()).collect()
            } else {
                vec![]
            };
            
            let allergies: Vec<String> = if rng.gen_bool(0.5) {
                (0..rng.gen_range(1..4)).map(|_| Word().fake()).collect()
            } else {
                vec![]
            };
            
            let password = hash_password("password");
            
            let patient = Patient {
                nom,
                prenom,
                email,
                telephone: PhoneNumber().fake(),
                adresse: StreetName().fake(),
                dateNaissance: birth_date.to_string(),
                groupeSanguin: blood_types.choose(&mut rng).unwrap().to_string(),
                numeroSecuriteSociale: numero_securite_sociale,
                antecedentsMedicaux: antecedents,
                allergies,
                dateInscription: date_inscription,
                password,
            };
            
            batch.push(doc! {
                "nom": patient.nom,
                "prenom": patient.prenom,
                "email": patient.email,
                "telephone": patient.telephone,
                "adresse": patient.adresse,
                "dateNaissance": patient.dateNaissance,
                "groupeSanguin": patient.groupeSanguin,
                "numeroSecuriteSociale": patient.numeroSecuriteSociale,
                "antecedentsMedicaux": patient.antecedentsMedicaux,
                "allergies": patient.allergies,
                "dateInscription": patient.dateInscription,
                "password": patient.password,
            });
        }
        
        // Insert batch
        match collection.insert_many(batch, None).await {
            Ok(result) => {
                debug!("Inserted batch {}/{} with {} patients", batch_idx + 1, num_batches, result.inserted_ids.len());
                pb.inc(current_batch_size as u64);
            },
            Err(e) => {
                error!("Failed to insert batch: {}", e);
                return Err(Box::new(e));
            }
        }
    }
    
    pb.finish_with_message("All patients generated successfully");
    info!("Successfully added {} patients to the database", count);
    
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    setup_logger(args.verbose);
    
    if args.number <= 0 {
        error!("Number of patients must be greater than 0");
        return Err("Number of patients must be greater than 0".into());
    }
    
    generate_patients(args.number).await?;
    
    Ok(())
}
