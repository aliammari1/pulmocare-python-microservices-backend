use clap::Parser;
use fake::faker::address::en::StreetName;
use fake::faker::internet::en::FreeEmail;
use fake::faker::name::en::{FirstName, LastName};
use fake::faker::phone_number::en::PhoneNumber;
use fake::{Fake, faker};
use fake::faker::name::raw::*;
use fake::faker::internet::raw::*;
use fake::faker::phone_number::raw::*;
use log::{info, debug, error};
use medapp_generators::{connect_to_mongodb, setup_logger, hash_password};
use mongodb::bson::{Document, doc};
use rand::{thread_rng, Rng, seq::SliceRandom};
use serde::{Deserialize, Serialize};
use std::error::Error;
use indicatif::{ProgressBar, ProgressStyle};
use chrono::{Utc, Duration};

#[derive(Debug, Serialize, Deserialize)]
struct Radiologue {
    nom: String,
    prenom: String,
    email: String,
    telephone: String,
    adresse: String,
    specialiteRadiologie: String,
    equipements: Vec<String>,
    dateInscription: String,
    numeroOrdre: String,
    password: String,
}

#[derive(Parser, Debug)]
#[clap(author, version, about = "Generate random radiologists")]
struct Args {
    #[clap(short, long, default_value_t = 5)]
    number: usize,
    
    #[clap(short, long)]
    verbose: bool,
}

async fn generate_radiologues(count: usize) -> Result<(), Box<dyn Error>> {
    let (db, _client) = connect_to_mongodb().await?;
    let collection = db.collection::<Document>("radiologues");
    
    let equipments = vec!["IRM", "Scanner", "Échographie", "Radiographie", "Mammographie"];
    let radiology_types = vec!["Général", "Neurologique", "Musculosquelettique", "Abdominale", "Thoracique"];
    
    info!("Starting generation of {} radiologists", count);
    
    let pb = ProgressBar::new(count as u64);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} radiologists generated ({eta})")
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
            
            let numero_ordre = format!("RD{}", (0..6).map(|_| rng.gen_range(0..10).to_string()).collect::<String>());
            
            // Randomly select 1 to 3 equipment items without duplicates
            let num_equipments = rng.gen_range(1..=3);
            let mut selected_equipments = Vec::new();
            let mut available_equipments = equipments.clone();
            
            for _ in 0..num_equipments {
                if available_equipments.is_empty() {
                    break;
                }
                let idx = rng.gen_range(0..available_equipments.len());
                selected_equipments.push(available_equipments.remove(idx).to_string());
            }
            
            let password = hash_password("password");
            
            let radiologue = Radiologue {
                nom,
                prenom,
                email,
                telephone: PhoneNumber().fake(),
                adresse: StreetName().fake(),
                specialiteRadiologie: radiology_types.choose(&mut rng).unwrap().to_string(),
                equipements: selected_equipments,
                dateInscription: date_inscription,
                numeroOrdre: numero_ordre.clone(),
                password,
            };
            
            batch.push(doc! {
                "nom": radiologue.nom,
                "prenom": radiologue.prenom,
                "email": radiologue.email,
                "telephone": radiologue.telephone,
                "adresse": radiologue.adresse,
                "specialiteRadiologie": radiologue.specialiteRadiologie,
                "equipements": radiologue.equipements,
                "dateInscription": radiologue.dateInscription,
                "numeroOrdre": radiologue.numeroOrdre,
                "password": radiologue.password,
            });
        }
        
        // Insert batch
        match collection.insert_many(batch, None).await {
            Ok(result) => {
                debug!("Inserted batch {}/{} with {} radiologists", batch_idx + 1, num_batches, result.inserted_ids.len());
                pb.inc(current_batch_size as u64);
            },
            Err(e) => {
                error!("Failed to insert batch: {}", e);
                return Err(Box::new(e));
            }
        }
    }
    
    pb.finish_with_message("All radiologists generated successfully");
    info!("Successfully added {} radiologists to the database", count);
    
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    setup_logger(args.verbose);
    
    if args.number <= 0 {
        error!("Number of radiologists must be greater than 0");
        return Err("Number of radiologists must be greater than 0".into());
    }
    
    generate_radiologues(args.number).await?;
    
    Ok(())
}
