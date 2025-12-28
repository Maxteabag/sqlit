# Outputs for test configuration
# These values are used by pytest to connect to the provisioned infrastructure

output "bucket_name" {
  description = "S3 bucket name for test data"
  value       = aws_s3_bucket.test_bucket.id
}

output "database_name" {
  description = "Glue database name"
  value       = aws_glue_catalog_database.test_db.name
}

output "workgroup" {
  description = "Athena workgroup name"
  value       = aws_athena_workgroup.test_workgroup.name
}

output "s3_staging_dir" {
  description = "S3 location for Athena query results"
  value       = "s3://${aws_s3_bucket.test_bucket.id}/results/"
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "test_id" {
  description = "Test run identifier"
  value       = local.test_id
}

# Output as JSON for easy parsing by test scripts
output "test_config" {
  description = "Complete test configuration as JSON"
  value = jsonencode({
    bucket_name    = aws_s3_bucket.test_bucket.id
    database_name  = aws_glue_catalog_database.test_db.name
    workgroup      = aws_athena_workgroup.test_workgroup.name
    s3_staging_dir = "s3://${aws_s3_bucket.test_bucket.id}/results/"
    aws_region     = var.aws_region
    test_id        = local.test_id
  })
}
