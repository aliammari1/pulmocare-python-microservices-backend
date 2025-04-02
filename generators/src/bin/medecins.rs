use clap::Parser;
use fake::faker::address::en::StreetName;
use fake::faker::internet::en::FreeEmail;
use fake::faker::name::en::{FirstName, LastName};
use fake::faker::phone_number::en::PhoneNumber;
use fake::{Fake, faker};
use fake::faker::name::raw::*;
use fake::faker::internet::raw::*;
use fake::faker::phone_number::raw::*;
use fake::faker::address::raw::*;
use log::{info, debug, error};
use medapp_generators::{connect_to_mongodb, setup_logger, hash_password};
use mongodb::bson::{Document, doc};
use rand::{thread_rng, Rng, seq::SliceRandom};
use serde::{Deserialize, Serialize};
use std::error::Error;
use indicatif::{ProgressBar, ProgressStyle};
use chrono::{Utc, Duration};

#[derive(Debug, Serialize, Deserialize)]
struct Doctor {
    nom: String,
    prenom: String,
    email: String,
    telephone: String,
    adresse: String,
    specialite: String,
    dateInscription: String,
    numeroOrdre: String,
    password: String,
}

#[derive(Parser, Debug)]
#[clap(author, version, about = "Generate random doctors")]
struct Args {
    #[clap(short, long, default_value_t = 10)]
    number: usize,
    
    #[clap(short, long)]
    verbose: bool,
}

async fn generate_doctors(count: usize) -> Result<(), Box<dyn Error>> {
    let (db, _client) = connect_to_mongodb().await?;
    let collection = db.collection::<Document>("doctors");
    
    let specialities = vec![
        "Cardiologue", "Dermatologue", "Neurologue", "Pédiatre", 
        "Radiologue", "Chirurgien", "Généraliste", "Ophtalmologue"
    ];
    
    info!("Starting generation of {} doctors", count);
    
    let pb = ProgressBar::new(count as u64);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} doctors generated ({eta})")
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
            let five_years_ago = now - Duration::days(365 * 5);
            let random_days = rng.gen_range(0..(now - five_years_ago).num_days());
            let date_inscription = (five_years_ago + Duration::days(random_days)).to_rfc3339();
            
            let nom = LastName().fake::<String>();
            let prenom = FirstName().fake::<String>();
            let email = FreeEmail().fake::<String>();
            
            let numero_ordre = format!("MD{}", (0..6).map(|_| rng.gen_range(0..10).to_string()).collect::<String>());
            
            let password = hash_password("password");
            
            let doctor = Doctor {
                nom,
                prenom,
                email,
                telephone: PhoneNumber().fake(),
                adresse: StreetName().fake(),
                specialite: specialities.choose(&mut rng).unwrap().to_string(),
                dateInscription: date_inscription,
                numeroOrdre: numero_ordre.clone(),
                password,
            };
            
            batch.push(doc! {
                "nom": doctor.nom,
                "prenom": doctor.prenom,
                "email": doctor.email,
                "telephone": doctor.telephone,
                "adresse": doctor.adresse,
                "specialite": doctor.specialite,
                "dateInscription": doctor.dateInscription,
                "numeroOrdre": doctor.numeroOrdre,
                "password": doctor.password,
            });
        }
        
        // Insert batch
        match collection.insert_many(batch, None).await {
            Ok(result) => {
                debug!("Inserted batch {}/{} with {} doctors", batch_idx + 1, num_batches, result.inserted_ids.len());
                pb.inc(current_batch_size as u64);
            },
            Err(e) => {
                error!("Failed to insert batch: {}", e);
                return Err(Box::new(e));
            }
        }
    }
    
    pb.finish_with_message("All doctors generated successfully");
    info!("Successfully added {} doctors to the database", count);
    
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    setup_logger(args.verbose);
    
    if args.number <= 0 {
        error!("Number of doctors must be greater than 0");
        return Err("Number of doctors must be greater than 0".into());
    }
    
    generate_doctors(args.number).await?;
    
    Ok(())
}
