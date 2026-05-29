# ── Dev Environment — Cost-minimized for demo purposes ────────────────────
# All expensive services (Redshift, MWAA) use smallest viable SKUs or
# are replaced with free-tier equivalents.

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # Remote state in S3 — bucket must exist before first init
  # Create manually once: aws s3 mb s3://econ-pipeline-tfstate-dev
  backend "s3" {
    # Values loaded from backend.hcl (git-ignored) — never hardcode here
    # backend.hcl contains: bucket, key, region, dynamodb_table
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "econ-pipeline"
      Environment = "dev"
      ManagedBy   = "terraform"
      CostCenter  = "demo"
    }
  }
}

# ── S3 Data Lake (free tier — just storage costs ~$0.023/GB) ─────────────
module "data_lake" {
  source      = "../../modules/s3"
  environment = var.environment
  project     = var.project
}

# ── Lambda Collectors (free tier: 1M requests/month) ─────────────────────
module "collectors" {
  source          = "../../modules/lambda"
  environment     = var.environment
  project         = var.project
  lambda_zip_path = var.lambda_zip_path
  s3_bucket_raw   = module.data_lake.raw_bucket_name

  # Secrets pulled from AWS Secrets Manager — not passed as env vars
  secrets_manager_arns = [
    aws_secretsmanager_secret.api_keys.arn
  ]
}

# ── Glue (dev uses Glue crawler + ETL — pay per DPU-hour, ~$0.44/DPU-hr) ─
# For demo: crawlers run on-demand only, not scheduled
module "glue" {
  source      = "../../modules/glue"
  environment = var.environment
  project     = var.project
  s3_buckets  = module.data_lake
}

# ── Secrets Manager — stores all API keys ────────────────────────────────
resource "aws_secretsmanager_secret" "api_keys" {
  name                    = "${var.project}/${var.environment}/api-keys"
  recovery_window_in_days = 0  # immediate delete ok for dev

  # Actual values set via: aws secretsmanager put-secret-value
  # NEVER put real keys in Terraform files
}

# ── EventBridge rules (free: 1M events/month) ─────────────────────────────
resource "aws_cloudwatch_event_rule" "daily_ingest" {
  name                = "${var.project}-${var.environment}-daily-ingest"
  description         = "Trigger daily market data collectors"
  schedule_expression = "cron(0 22 ? * MON-FRI *)"  # 5pm ET close
  state               = "DISABLED"  # enable manually when testing to avoid costs
}

resource "aws_cloudwatch_event_rule" "monthly_macro" {
  name                = "${var.project}-${var.environment}-monthly-macro"
  description         = "Trigger FRED/BLS macro data collectors"
  schedule_expression = "cron(0 15 15 * ? *)"  # 15th of each month
  state               = "DISABLED"
}

# ── Athena workgroup with cost controls ───────────────────────────────────
resource "aws_athena_workgroup" "analysts" {
  name = "${var.project}-${var.environment}"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${module.data_lake.raw_bucket_name}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }

    # Hard limit: no single query can scan more than 1GB (cost guard)
    bytes_scanned_cutoff_per_query = 1073741824
  }
}

# ── NOTE: Redshift OMITTED for dev ───────────────────────────────────────
# Redshift dc2.large = ~$0.25/hr = $180/month minimum
# For demo: use Athena + S3 Parquet instead (pay per query, ~$5/TB scanned)
# Redshift module is defined but only deployed to prod via environments/prod/
