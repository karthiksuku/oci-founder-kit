resource "google_cloud_run_v2_service" "api" {
  name     = "taskboard-api"
  location = "australia-southeast1"
}

resource "google_sql_database_instance" "main" {
  name             = "taskboard"
  database_version = "POSTGRES_15"
}

module "reporting_db" {
  source  = "GoogleCloudPlatform/sql-db/google//modules/mysql"
  version = "~> 20.0"
}

resource "google_storage_bucket" "uploads" {
  name = "taskboard-uploads"
}

resource "google_pubsub_topic" "events" {
  name = "taskboard-events"
}

resource "google_secret_manager_secret" "db" {
  secret_id = "db-password"
}

resource "google_redis_instance" "cache" {
  name = "taskboard"
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "taskboard"
}

resource "google_compute_network" "main" {
  name = "taskboard"
}
