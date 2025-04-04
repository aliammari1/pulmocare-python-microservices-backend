use chrono::{Duration, Utc};
use clap::Parser;
use fake::faker::address::en::StreetName;
use fake::faker::address::raw::*;
use fake::faker::internet::en::FreeEmail;
use fake::faker::internet::raw::*;
use fake::faker::name::en::{FirstName, LastName};
use fake::faker::name::raw::*;
use fake::faker::phone_number::en::PhoneNumber;
use fake::faker::phone_number::raw::*;
use fake::{faker, Fake};
use indicatif::{ProgressBar, ProgressStyle};
use log::{debug, error, info};
use medapp_generators::{connect_to_mongodb, hash_password, setup_logger};
use mongodb::bson::{doc, Document};
use rand::{seq::SliceRandom, thread_rng, Rng};
use serde::{Deserialize, Serialize};
use std::error::Error;

#[derive(Debug, Serialize, Deserialize)]
struct Doctor {
    name: String,
    email: String,
    specialty: String,
    phone_number: String,
    address: String,
    password_hash: String,
    is_verified: bool,
    profile_image: Option<String>,
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
        "Cardiology",
        "Dermatology",
        "Neurology",
        "Pediatrics",
        "Radiology",
        "Surgery",
        "General Medicine",
        "Ophthalmology",
        "Gynecology",
        "Orthopedics",
        "Psychiatry",
        "Urology",
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

            let name = format!(
                "{} {}",
                FirstName().fake::<String>(),
                LastName().fake::<String>()
            );
            let email = FreeEmail().fake::<String>();

            let password_hash = hash_password("password");

            let doctor = Doctor {
                name,
                email,
                specialty: specialities.choose(&mut rng).unwrap().to_string(),
                phone_number: PhoneNumber().fake(),
                address: StreetName().fake(),
                password_hash,
                is_verified: rng.gen_bool(0.5),
                profile_image: None,
            };

            batch.push(doc! {
                "name": doctor.name,
                "email": doctor.email,
                "specialty": doctor.specialty,
                "phone_number": doctor.phone_number,
                "address": doctor.address,
                "password_hash": doctor.password_hash,
                "is_verified": doctor.is_verified,
                "profile_image": doctor.profile_image,
            });
        }

        // Insert batch
        match collection.insert_many(batch, None).await {
            Ok(result) => {
                debug!(
                    "Inserted batch {}/{} with {} doctors",
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
