variable "environment" {
  type = string
}

variable "project" {
  type = string
}

variable "s3_buckets" {
  type = object({
    raw_bucket_name     = string
    clean_bucket_name   = string
    curated_bucket_name = string
    raw_bucket_arn      = string
    clean_bucket_arn    = string
    curated_bucket_arn  = string
  })
}
