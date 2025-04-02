use clap::Parser;
use log::{error, info};
use medapp_generators::{connect_to_mongodb, setup_logger};
use mongodb::bson::doc;
use mongodb::options::IndexOptions;
use mongodb::IndexModel;
use std::error::Error;

#[derive(Parser, Debug)]
#[clap(
    author,
    version,
    about = "Create optimal indexes for MongoDB collections"
)]
struct Args {
    #[clap(short, long)]
    verbose: bool,
}

async fn create_indexes() -> Result<(), Box<dyn Error>> {
    let (db, _client) = connect_to_mongodb().await?;

    // Create indexes for patients collection
    info!("Creating indexes for patients collection");
    let patients_collection = db.collection::<mongodb::bson::Document>("patients");
    let patient_indexes = vec![
        IndexModel::builder()
            .keys(doc! { "email": 1 })
            .options(IndexOptions::builder().unique(true).build())
            .build(),
        IndexModel::builder()
            .keys(doc! { "numeroSecuriteSociale": 1 })
            .options(IndexOptions::builder().unique(true).build())
            .build(),
    ];
    patients_collection
        .create_indexes(patient_indexes, None)
        .await?;

    // Create indexes for medecins collection
    info!("Creating indexes for medecins collection");
    let medecins_collection = db.collection::<mongodb::bson::Document>("medecins");
    let medecin_indexes = vec![
        IndexModel::builder()
            .keys(doc! { "email": 1 })
            .options(IndexOptions::builder().unique(true).build())
            .build(),
        IndexModel::builder()
            .keys(doc! { "numeroOrdre": 1 })
            .options(IndexOptions::builder().unique(true).build())
            .build(),
    ];
    medecins_collection
        .create_indexes(medecin_indexes, None)
        .await?;

    // Create indexes for radiologues collection
    info!("Creating indexes for radiologues collection");
    let radiologues_collection = db.collection::<mongodb::bson::Document>("radiologues");
    let radiologue_indexes = vec![
        IndexModel::builder()
            .keys(doc! { "email": 1 })
            .options(IndexOptions::builder().unique(true).build())
            .build(),
        IndexModel::builder()
            .keys(doc! { "numeroOrdre": 1 })
            .options(IndexOptions::builder().unique(true).build())
            .build(),
    ];
    radiologues_collection
        .create_indexes(radiologue_indexes, None)
        .await?;

    // Create indexes for reports collection
    info!("Creating indexes for reports collection");
    let reports_collection = db.collection::<mongodb::bson::Document>("reports");
    let report_indexes = vec![
        IndexModel::builder().keys(doc! { "patient_id": 1 }).build(),
        IndexModel::builder()
            .keys(doc! { "radiologue_id": 1 })
            .build(),
        IndexModel::builder().keys(doc! { "medecin_id": 1 }).build(),
    ];
    reports_collection
        .create_indexes(report_indexes, None)
        .await?;

    // Create indexes for ordonnances collection
    info!("Creating indexes for ordonnances collection");
    let ordonnances_collection = db.collection::<mongodb::bson::Document>("ordonnances");
    let ordonnance_indexes = vec![
        IndexModel::builder().keys(doc! { "patient_id": 1 }).build(),
        IndexModel::builder().keys(doc! { "medecin_id": 1 }).build(),
    ];
    ordonnances_collection
        .create_indexes(ordonnance_indexes, None)
        .await?;

    info!("All indexes created successfully");
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    setup_logger(args.verbose);

    create_indexes().await?;

    Ok(())
}
