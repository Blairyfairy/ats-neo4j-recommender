output "dashboard_url" {
  description = "ALB URL for the outlier recommendation dashboard"
  value       = var.acm_certificate_arn != "" ? "https://${aws_lb.app.dns_name}" : "http://${aws_lb.app.dns_name}"
}

output "alb_dns_name" {
  value = aws_lb.app.dns_name
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "analysis_bucket" {
  value = aws_s3_bucket.analysis.id
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "secret_arn" {
  value = aws_secretsmanager_secret.neo4j.arn
}

output "pipeline_state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}

output "neo4j_privatelink_endpoint_id" {
  value = try(aws_vpc_endpoint.neo4j[0].id, null)
}
