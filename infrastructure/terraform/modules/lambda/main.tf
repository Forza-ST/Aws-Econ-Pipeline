# ── Lambda Module — Collector functions ──────────────────────────────────
# Free tier: 1M requests/month, 400,000 GB-seconds compute/month
# All collectors run under 128MB, <30s → well within free tier for demo

resource "aws_iam_role" "lambda_exec" {
  name = "${var.project}-${var.environment}-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_s3" {
  name = "s3-write-raw"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Least privilege: write to raw bucket only, specific prefix
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${local.s3_bucket_raw_arn}/raw/*"
      },
      {
        # Read secrets — only the api-keys secret
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.secrets_manager_arns
      },
      {
        # CloudWatch logs (required for Lambda)
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# One Lambda per data source — isolated failure domains
locals {
  s3_bucket_raw_arn = var.s3_bucket_raw_arn != "" ? var.s3_bucket_raw_arn : "arn:aws:s3:::${var.s3_bucket_raw}"

  collectors = {
    fred     = { handler = "fred_collector.lambda_handler", timeout = 60, memory = 128 }
    bls      = { handler = "bls_collector.lambda_handler", timeout = 60, memory = 128 }
    yfinance = { handler = "yfinance_collector.lambda_handler", timeout = 120, memory = 256 }
    forex    = { handler = "forex_collector.lambda_handler", timeout = 30, memory = 128 }
  }
}

resource "aws_lambda_function" "collectors" {
  for_each = local.collectors

  function_name = "${var.project}-${var.environment}-${each.key}-collector"
  role          = aws_iam_role.lambda_exec.arn
  handler       = each.value.handler
  runtime       = "python3.11"
  timeout       = each.value.timeout
  memory_size   = each.value.memory # keep low for cost

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      ENVIRONMENT   = var.environment
      S3_BUCKET_RAW = var.s3_bucket_raw
      # API keys NOT here — Lambda fetches from Secrets Manager at runtime
      SECRETS_ARN = var.secrets_manager_arns[0]
    }
  }
}
