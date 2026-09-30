variable "aws_region" {
  description = "AWS region (use one with >= 3 AZs)"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "enable_nat_gateway" {
  description = "NAT for private-subnet outbound (needed if Aura is public TLS; optional with full PrivateLink + endpoints)"
  type        = bool
  default     = true
}

variable "app_image" {
  description = "ECR image URI including tag"
  type        = string
}

variable "neo4j_uri" {
  description = "Neo4j AuraDB URI (neo4j+s://… or private endpoint hostname)"
  type        = string
}

variable "neo4j_user" {
  type    = string
  default = "neo4j"
}

variable "neo4j_password" {
  type      = string
  sensitive = true
}

variable "neo4j_database" {
  type    = string
  default = "neo4j"
}

variable "neo4j_privatelink_service_name" {
  description = "Aura PrivateLink service name from console (Enterprise). Empty = public TLS."
  type        = string
  default     = ""
}

variable "neo4j_privatelink_private_dns" {
  type    = bool
  default = true
}

variable "acm_certificate_arn" {
  description = "ACM cert ARN in this region for HTTPS. Empty = HTTP only."
  type        = string
  default     = ""
}

variable "task_cpu" {
  type    = string
  default = "512"
}

variable "task_memory" {
  type    = string
  default = "1024"
}

variable "desired_count" {
  description = "Minimum Fargate tasks (use >= 2 for multi-AZ HA)"
  type        = number
  default     = 2
}

variable "enable_autoscaling" {
  type    = bool
  default = true
}

variable "max_capacity" {
  type    = number
  default = 6
}

variable "pipeline_schedule" {
  description = "EventBridge schedule for the ATS batch pipeline"
  type        = string
  default     = "cron(0 2 * * ? *)"
}
