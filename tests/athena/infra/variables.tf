# Input variables for Athena test infrastructure

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "test_id" {
  description = "Unique identifier for this test run (used in resource names)"
  type        = string
  default     = ""
}
