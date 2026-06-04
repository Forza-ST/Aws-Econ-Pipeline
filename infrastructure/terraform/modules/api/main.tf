variable "environment" { type = string }
variable "project" { type = string }
variable "api_zip_path" { type = string }
variable "s3_bucket_clean" { type = string }
variable "s3_bucket_curated" { type = string }
variable "s3_bucket_raw" { type = string }
variable "s3_bucket_clean_arn" { type = string }
variable "s3_bucket_curated_arn" { type = string }
variable "s3_bucket_raw_arn" { type = string }
variable "athena_workgroup" { type = string }
variable "glue_database_name" { type = string }

resource "aws_iam_role" "api_exec" {
  name = "${var.project}-${var.environment}-api-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "api_access" {
  name = "athena-s3-read"
  role = aws_iam_role.api_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StopQueryExecution",
          "athena:GetWorkGroup",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:AbortMultipartUpload",
          "s3:PutObject",
        ]
        Resource = [
          var.s3_bucket_clean_arn,
          "${var.s3_bucket_clean_arn}/*",
          var.s3_bucket_curated_arn,
          "${var.s3_bucket_curated_arn}/*",
          var.s3_bucket_raw_arn,
          "${var.s3_bucket_raw_arn}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Athena tables for market + forecast Parquet (fred + correlation created manually in Phase 6)
resource "aws_glue_catalog_table" "market_prices" {
  name          = "market_prices"
  database_name = var.glue_database_name

  table_type = "EXTERNAL_TABLE"
  parameters = { "classification" = "parquet" }

  storage_descriptor {
    location      = "s3://${var.s3_bucket_clean}/clean/market/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "symbol"
      type = "string"
    }
    columns {
      name = "date"
      type = "date"
    }
    columns {
      name = "open"
      type = "double"
    }
    columns {
      name = "high"
      type = "double"
    }
    columns {
      name = "low"
      type = "double"
    }
    columns {
      name = "close"
      type = "double"
    }
    columns {
      name = "volume"
      type = "bigint"
    }
    columns {
      name = "source"
      type = "string"
    }
  }
}

locals {
  forecast_tables = {
    cpi_forecast               = "cpi_forecast.parquet"
    unemployment_rate_forecast = "unemployment_rate_forecast.parquet"
    wti_oil_forecast           = "wti_oil_forecast.parquet"
    gold_forecast              = "gold_forecast.parquet"
  }
}

resource "aws_glue_catalog_table" "forecasts" {
  for_each      = local.forecast_tables
  name          = each.key
  database_name = var.glue_database_name

  table_type = "EXTERNAL_TABLE"
  parameters = { "classification" = "parquet" }

  storage_descriptor {
    location      = "s3://${var.s3_bucket_curated}/curated/forecasts/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "ds"
      type = "timestamp"
    }
    columns {
      name = "yhat"
      type = "double"
    }
    columns {
      name = "yhat_lower"
      type = "double"
    }
    columns {
      name = "yhat_upper"
      type = "double"
    }
    columns {
      name = "series"
      type = "string"
    }
    columns {
      name = "is_forecast"
      type = "boolean"
    }
  }
}

resource "aws_lambda_function" "dashboard_api" {
  function_name = "${var.project}-${var.environment}-dashboard-api"
  role          = aws_iam_role.api_exec.arn
  handler       = "dashboard_api.lambda_handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 256

  filename         = var.api_zip_path
  source_code_hash = filebase64sha256(var.api_zip_path)

  environment {
    variables = {
      ATHENA_WORKGROUP = var.athena_workgroup
      ATHENA_DATABASE  = "econ_db"
      ATHENA_OUTPUT    = "s3://${var.s3_bucket_raw}/athena-results/"
    }
  }
}

resource "aws_apigatewayv2_api" "dashboard" {
  name          = "${var.project}-${var.environment}-dashboard"
  protocol_type = "HTTP"
  description   = "Econ pipeline dashboard API — Athena over live S3 Parquet"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.dashboard.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.dashboard_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.dashboard.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.dashboard.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.dashboard.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dashboard_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.dashboard.execution_arn}/*/*"
}

output "api_url" {
  value = aws_apigatewayv2_api.dashboard.api_endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.dashboard_api.function_name
}
