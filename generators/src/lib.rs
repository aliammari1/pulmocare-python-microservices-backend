use log::{error, info};
use mongodb::{
    options::{ClientOptions, WriteConcern},
    Client, Database,
};
use std::error::Error;
use std::time::Duration;

pub async fn connect_to_mongodb() -> Result<(Database, Client), Box<dyn Error>> {
    info!("Connecting to MongoDB container...");

    // Create a client options struct with optimized settings for container environment
    let mut client_options = ClientOptions::parse("mongodb://admin:admin@localhost:27017").await?;

    // Set application name for better monitoring
    client_options.app_name = Some("medapp-generator".to_string());

    // Optimize connection pool for batch operations
    client_options.max_pool_size = Some(20);
    client_options.min_pool_size = Some(5);

    // Set socket timeout options
    client_options.connect_timeout = Some(Duration::from_secs(5));
    client_options.server_selection_timeout = Some(Duration::from_secs(5));

    // Optimize write concern for bulk inserts
    // "acknowledged" is generally a good balance for generated test data
    // For faster inserts at the cost of reliability, you could use w: 0
    let write_concern = WriteConcern::builder()
        .w(mongodb::options::Acknowledgment::Majority)
        .journal(false)
        .build();
    client_options.write_concern = Some(write_concern);

    // Create the client
    let client = Client::with_options(client_options)?;

    // Ping the server to ensure connection is established
    client
        .database("admin")
        .run_command(mongodb::bson::doc! {"ping": 1}, None)
        .await?;

    let db = client.database("medapp");
    info!("Connected to MongoDB container successfully");
    Ok((db, client))
}

pub fn setup_logger(verbose: bool) {
    let mut builder = env_logger::Builder::from_default_env();

    if verbose {
        builder.filter_level(log::LevelFilter::Debug);
    } else {
        builder.filter_level(log::LevelFilter::Info);
    }

    builder.init();
}

// Hash password with bcrypt
pub fn hash_password(password: &str) -> String {
    bcrypt::hash(password, bcrypt::DEFAULT_COST).unwrap_or_else(|e| {
        error!("Failed to hash password: {}", e);
        panic!("Password hashing failed");
    })
}
