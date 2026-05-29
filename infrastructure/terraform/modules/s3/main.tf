# ── S3 Data Lake Module ──────────────────────────────────────────────────
# Three-zone lake: raw (bronze) → clean (silver) → curated (gold)
# All buckets: versioning, encryption, public access blocked

locals {
  buckets = {
    raw     = "${var.project}-raw-${var.environment}"
    clean   = "${var.project}-clean-${var.environment}"
    curated = "${var.project}-curated-${var.environment}"
    logs    = "${var.project}-logs-${var.environment}"
  }
}

resource "aws_s3_bucket" "lake" {
  for_each = local.buckets
  bucket   = each.value

  lifecycle {
    prevent_destroy = false  # set true in prod
  }
}

resource "aws_s3_bucket_versioning" "lake" {
  for_each = aws_s3_bucket.lake
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  for_each = aws_s3_bucket.lake
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"  # SSE-S3, free — SSE-KMS costs $1/10k requests
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  for_each                = aws_s3_bucket.lake
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: auto-expire raw files after 90 days to control storage costs
resource "aws_s3_bucket_lifecycle_configuration" "raw_expire" {
  bucket = aws_s3_bucket.lake["raw"].id
  rule {
    id     = "expire-raw-90d"
    status = "Enabled"
    filter { prefix = "" }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"   # 30 days → cheaper tier
    }
    expiration { days = 90 }          # delete after 90 days in dev
  }
}

# Logging bucket — server access logs for audit trail
resource "aws_s3_bucket_logging" "lake" {
  for_each      = { for k, v in aws_s3_bucket.lake : k => v if k != "logs" }
  bucket        = each.value.id
  target_bucket = aws_s3_bucket.lake["logs"].id
  target_prefix = "${each.key}/"
}

output "raw_bucket_name"     { value = aws_s3_bucket.lake["raw"].id }
output "clean_bucket_name"   { value = aws_s3_bucket.lake["clean"].id }
output "curated_bucket_name" { value = aws_s3_bucket.lake["curated"].id }
output "raw_bucket_arn"      { value = aws_s3_bucket.lake["raw"].arn }
output "clean_bucket_arn"    { value = aws_s3_bucket.lake["clean"].arn }
output "curated_bucket_arn"  { value = aws_s3_bucket.lake["curated"].arn }
