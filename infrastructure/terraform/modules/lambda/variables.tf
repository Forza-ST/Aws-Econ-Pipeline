variable "environment" {}
variable "project" {}
variable "lambda_zip_path" {}
variable "s3_bucket_raw" {}
variable "s3_bucket_raw_arn" { default = "" }
variable "secrets_manager_arns" { type = list(string) }
