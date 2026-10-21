terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  name    = "taskboard"
}

resource "aws_security_group" "api" {
  name   = "api"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port = 443
    to_port   = 443
    protocol  = "tcp"
  }
}

resource "aws_ecr_repository" "api" {
  name = "taskboard-api"
}

resource "aws_ecs_cluster" "main" {
  name = "taskboard"
}

resource "aws_ecs_task_definition" "api" {
  family                = "api"
  container_definitions = jsonencode([{ name = "api", image = "api:latest" }])
}

resource "aws_ecs_service" "api" {
  name    = "api"
  cluster = aws_ecs_cluster.main.id
}

resource "aws_lb" "web" {
  name               = "taskboard"
  load_balancer_type = "application"
}

resource "aws_db_instance" "main" {
  identifier     = "taskboard"
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = "db.t4g.medium"
  tags = {
    engine = "not-the-engine"
  }
}

resource "aws_s3_bucket" "uploads" {
  bucket = "taskboard-uploads"
}

resource "aws_elasticache_replication_group" "cache" {
  replication_group_id = "taskboard"
  engine               = "redis"
}

resource "aws_sqs_queue" "jobs" {
  name = "taskboard-jobs"
}

resource "aws_cognito_user_pool" "users" {
  name = "taskboard-users"
}

resource "aws_secretsmanager_secret" "db" {
  name = "taskboard/db"
}

resource "aws_route53_record" "www" {
  name = "www"
  type = "CNAME"
}

resource "aws_cloudfront_distribution" "web" {
  enabled = true
}

resource "aws_cloudwatch_log_group" "api" {
  name = "/ecs/api"
}

resource "aws_xray_sampling_rule" "api" {
  rule_name = "api"
}

resource "aws_appconfig_application" "flags" {
  name = "taskboard-flags"
}

data "aws_caller_identity" "current" {}
