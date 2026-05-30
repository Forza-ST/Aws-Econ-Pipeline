# ── Glue Module — Python Shell ETL + on-demand crawler (dev) ─────────────

resource "aws_iam_role" "glue_etl" {
  name = "${var.project}-${var.environment}-glue-etl"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_etl.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3" {
  name = "glue-s3-access"
  role = aws_iam_role.glue_etl.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Resource = [
        var.s3_buckets.raw_bucket_arn,
        "${var.s3_buckets.raw_bucket_arn}/*",
        var.s3_buckets.clean_bucket_arn,
        "${var.s3_buckets.clean_bucket_arn}/*",
        var.s3_buckets.curated_bucket_arn,
        "${var.s3_buckets.curated_bucket_arn}/*",
      ]
    }]
  })
}

resource "aws_glue_catalog_database" "econ" {
  # Glue catalog names: lowercase letters, numbers, underscores only
  name = replace("${var.project}_${var.environment}_db", "-", "_")
}

resource "aws_glue_job" "silver_transform" {
  name     = "${var.project}-silver-transform"
  role_arn = aws_iam_role.glue_etl.arn

  command {
    name            = "pythonshell"
    python_version  = "3.9"
    script_location = "s3://${var.s3_buckets.raw_bucket_name}/glue-scripts/glue_silver_job.py"
  }

  default_arguments = {
    "--raw_bucket"   = var.s3_buckets.raw_bucket_name
    "--clean_bucket" = var.s3_buckets.clean_bucket_name
    "--job-language" = "python"
  }

  max_capacity = 0.0625 # 1/16 DPU — minimum for Python Shell
  timeout      = 60
}

resource "aws_glue_crawler" "raw_crawler" {
  name          = "${var.project}-${var.environment}-raw-crawler"
  role          = aws_iam_role.glue_etl.arn
  database_name = aws_glue_catalog_database.econ.name

  s3_target {
    path = "s3://${var.s3_buckets.raw_bucket_name}/raw/"
  }

  schema_change_policy {
    delete_behavior = "LOG"
  }
}

output "glue_job_name" {
  value = aws_glue_job.silver_transform.name
}
