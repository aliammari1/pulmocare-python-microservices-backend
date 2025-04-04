use clap::Parser;
use fake::Fake;
use fake::faker::lorem::en::Paragraph;
use log::{info, debug, error};
use medapp_generators::{connect_to_mongodb, setup_logger};
use mongodb::bson::{self, doc, oid::ObjectId, Document};
use rand::{thread_rng, Rng, seq::SliceRandom};
use serde::{Deserialize, Serialize};
use std::error::Error;
use indicatif::{ProgressBar, ProgressStyle};
use chrono::{Utc, Duration};
use futures::StreamExt;
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize)]
struct Finding {
    condition: String,
    severity: String,
    description: String,
    confidence_score: f64,
    probability: f64,
}

#[derive(Debug, Serialize, Deserialize)]
struct ImageQualityMetrics {
    contrast: String,
    sharpness: String,
    exposure: String,
    positioning: String,
    noise_level: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct TechnicalDetails {
    quality_metrics: ImageQualityMetrics,
    image_stats: std::collections::HashMap<String, String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct Analysis {
    findings: Vec<Finding>,
    technical_details: TechnicalDetails,
}

#[derive(Debug, Serialize, Deserialize)]
struct Report {
    title: String,
    content: String,
    patient_id: ObjectId,
    doctor_id: ObjectId,
    radiologist_id: ObjectId,
    exam_type: String,
    body_part: String,
    exam_date: String,
    conclusion: String,
    analysis: Option<Analysis>,
    tags: Vec<String>,
    image_path: String,
}

#[derive(Parser, Debug)]
#[clap(author, version, about = "Generate random radiology reports")]
struct Args {
    #[clap(short, long, default_value_t = 30)]
    number: usize,
    
    #[clap(short, long)]
    verbose: bool,
}

// Cache IDs from the database to avoid repeated queries
async fn cache_ids(db: &mongodb::Database) -> Result<(Vec<ObjectId>, Vec<ObjectId>, Vec<ObjectId>), Box<dyn Error>> {
    info!("Caching patient, radiologist, and doctor IDs");
    
    let patients_collection = db.collection::<Document>("patients");
    let radiologues_collection = db.collection::<Document>("radiologues");
    let medecins_collection = db.collection::<Document>("doctors");
    
    // Fix cursor processing to properly handle MongoDB results
    let mut patient_cursor = patients_collection.find(None, None).await?;
    let mut patient_ids = Vec::new();
    while let Some(result) = patient_cursor.next().await {
        let document = result?;
        patient_ids.push(document.get_object_id("_id").unwrap().clone());
    }
    
    let mut radiologue_cursor = radiologues_collection.find(None, None).await?;
    let mut radiologue_ids = Vec::new();
    while let Some(result) = radiologue_cursor.next().await {
        let document = result?;
        radiologue_ids.push(document.get_object_id("_id").unwrap().clone());
    }
    
    let mut medecin_cursor = medecins_collection.find(None, None).await?;
    let mut medecin_ids = Vec::new();
    while let Some(result) = medecin_cursor.next().await {
        let document = result?;
        medecin_ids.push(document.get_object_id("_id").unwrap().clone());
    }
    
    if patient_ids.is_empty() || radiologue_ids.is_empty() || medecin_ids.is_empty() {
        return Err("Missing required entities in the database. Please generate them first.".into());
    }
    
    info!(
        "Cached {} patient IDs, {} radiologist IDs, and {} doctor IDs",
        patient_ids.len(), radiologue_ids.len(), medecin_ids.len()
    );
    
    Ok((patient_ids, radiologue_ids, medecin_ids))
}

// Generate a random report using cached IDs
fn generate_report(
    patient_ids: &[ObjectId], 
    radiologue_ids: &[ObjectId], 
    medecin_ids: &[ObjectId]
) -> Report {
    let mut rng = thread_rng();
    
    let report_types = vec!["IRM", "Scanner", "Échographie", "Radiographie", "Mammographie"];
    let body_parts = vec!["Tête", "Thorax", "Abdomen", "Membres inférieurs", "Membres supérieurs", "Colonne vertébrale", "Bassin"];
    let findings = vec!["Normal", "Légère anomalie", "Anomalie significative", "Résultats préoccupants", "Résultats critiques"];
    
    let now = Utc::now();
    let six_months_ago = now - Duration::days(180);
    let random_days = rng.gen_range(0..(now - six_months_ago).num_days());
    let date_examen = (six_months_ago + Duration::days(random_days)).to_rfc3339();
    
    let recommendations = if rng.gen_bool(0.7) {
        Some(Paragraph(1..2))
    } else {
        None
    };
    
    let image_uuid = Uuid::new_v4();
    
    Report {
        title: "Random Report Title".to_string(),
        content: "Random Report Content".to_string(),
        patient_id: patient_ids.choose(&mut rng).unwrap().clone(),
        radiologist_id: radiologue_ids.choose(&mut rng).unwrap().clone(),
        doctor_id: medecin_ids.choose(&mut rng).unwrap().clone(),
        exam_type: report_types.choose(&mut rng).unwrap().to_string(),
        body_part: body_parts.choose(&mut rng).unwrap().to_string(),
        exam_date: date_examen,
        conclusion: findings.choose(&mut rng).unwrap().to_string(),
        analysis: None,
        tags: vec!["tag1".to_string(), "tag2".to_string()],
        image_path: format!("/images/reports/{}.jpg", image_uuid),
    }
}

async fn generate_reports(count: usize) -> Result<(), Box<dyn Error>> {
    let (db, _client) = connect_to_mongodb().await?;
    let collection = db.collection::<Document>("reports");
    
    // Cache IDs for better performance
    let (patient_ids, radiologue_ids, medecin_ids) = cache_ids(&db).await?;
    
    info!("Starting generation of {} reports", count);
    
    let pb = ProgressBar::new(count as u64);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} reports generated ({eta})")
        .unwrap()
        .progress_chars("#>-"));
    
    // Process in batches of 100 for better performance
    let batch_size = 100;
    let num_batches = (count + batch_size - 1) / batch_size;
    
    for batch_idx in 0..num_batches {
        let mut batch = Vec::with_capacity(batch_size);
        let current_batch_size = std::cmp::min(batch_size, count - batch_idx * batch_size);
        
        for _ in 0..current_batch_size {
            let report = generate_report(&patient_ids, &radiologue_ids, &medecin_ids);
            
            let mut doc = doc! {
                "title": report.title,
                "content": report.content,
                "patient_id": report.patient_id,
                "radiologist_id": report.radiologist_id,
                "doctor_id": report.doctor_id,
                "exam_type": report.exam_type,
                "body_part": report.body_part,
                "exam_date": report.exam_date,
                "conclusion": report.conclusion,
                "image_path": report.image_path,
                "tags": report.tags,
            };
            
            if let Some(analysis) = report.analysis {
                doc.insert("analysis", bson::to_bson(&analysis)?);
            }
            
            batch.push(doc);
        }
        
        // Insert batch
        match collection.insert_many(batch, None).await {
            Ok(result) => {
                debug!("Inserted batch {}/{} with {} reports", batch_idx + 1, num_batches, result.inserted_ids.len());
                pb.inc(current_batch_size as u64);
            },
            Err(e) => {
                error!("Failed to insert batch: {}", e);
                return Err(Box::new(e));
            }
        }
    }
    
    pb.finish_with_message("All reports generated successfully");
    info!("Successfully added {} reports to the database", count);
    
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    setup_logger(args.verbose);
    
    if args.number <= 0 {
        error!("Number of reports must be greater than 0");
        return Err("Number of reports must be greater than 0".into());
    }
    
    generate_reports(args.number).await?;
    
    Ok(())
}
