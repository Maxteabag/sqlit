# Ephemeral AWS Athena infrastructure for integration testing
# This creates temporary resources that are destroyed after tests complete

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "sqlit"
      Environment = "test"
      ManagedBy   = "terraform"
      TestId      = var.test_id
    }
  }
}

# Generate a random suffix if test_id not provided
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  test_id     = var.test_id != "" ? var.test_id : random_id.suffix.hex
  bucket_name = "sqlit-athena-test-${local.test_id}"
  db_name     = "sqlit_test_${local.test_id}"
}

# -----------------------------------------------------------------------------
# S3 Bucket for test data and query results
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "test_bucket" {
  bucket        = local.bucket_name
  force_destroy = true # Allow deletion even with objects inside
}

resource "aws_s3_bucket_public_access_block" "test_bucket" {
  bucket = aws_s3_bucket.test_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Upload test CSV data for Hive table
resource "aws_s3_object" "hive_test_data" {
  bucket       = aws_s3_bucket.test_bucket.id
  key          = "hive_data/data.csv"
  content_type = "text/csv"
  content      = <<-EOF
    id,name
    1,Alice
    2,Bob
    3,Charlie
  EOF
}

# -----------------------------------------------------------------------------
# Glue Catalog Database
# -----------------------------------------------------------------------------
resource "aws_glue_catalog_database" "test_db" {
  name        = local.db_name
  description = "Temporary test database for sqlit Athena adapter"
}

# -----------------------------------------------------------------------------
# Glue Catalog Table (Hive/CSV format)
# -----------------------------------------------------------------------------
resource "aws_glue_catalog_table" "hive_table" {
  name          = "test_hive_table"
  database_name = aws_glue_catalog_database.test_db.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "skip.header.line.count" = "1"
    "classification"         = "csv"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.test_bucket.id}/hive_data/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "csv-serde"
      serialization_library = "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"
      parameters = {
        "field.delim"            = ","
        "serialization.format"   = ","
        "skip.header.line.count" = "1"
      }
    }

    columns {
      name = "id"
      type = "int"
    }

    columns {
      name = "name"
      type = "string"
    }
  }
}

# -----------------------------------------------------------------------------
# Athena Workgroup with cost controls
# -----------------------------------------------------------------------------
resource "aws_athena_workgroup" "test_workgroup" {
  name          = "sqlit-test-${local.test_id}"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false

    result_configuration {
      output_location = "s3://${aws_s3_bucket.test_bucket.id}/results/"
    }

    # Cost control: limit to 1GB scanned per query
    bytes_scanned_cutoff_per_query = 1073741824
  }
}

# -----------------------------------------------------------------------------
# Create a view for testing get_views()
# -----------------------------------------------------------------------------
# Note: Views must be created via Athena query, not Glue directly
# We use a null_resource with local-exec to create the view after infrastructure is ready

resource "null_resource" "create_view" {
  depends_on = [
    aws_glue_catalog_table.hive_table,
    aws_athena_workgroup.test_workgroup
  ]

  provisioner "local-exec" {
    command     = "python3 create_view.py ${local.db_name} ${aws_athena_workgroup.test_workgroup.name} s3://${aws_s3_bucket.test_bucket.id}/results/ ${var.aws_region}"
    working_dir = path.module
  }

  provisioner "local-exec" {
    when    = destroy
    command = "echo 'View will be destroyed with database'"
  }
}
