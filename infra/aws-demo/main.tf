terraform {
  required_version = "= 1.16.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = { Project = "ProofOps", Environment = "isolated-demo", ManagedBy = "Terraform" }
  }
}

resource "aws_cloudwatch_log_group" "demo" {
  name              = "/proofops/${var.name}"
  retention_in_days = 1
}

resource "aws_ecs_cluster" "demo" {
  name = var.name
}

resource "aws_iam_role" "execution" {
  name = "${var.name}-execution"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = var.ecr_repository_arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.demo.arn}:*" }
    ]
  })
}

resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = aws_iam_role.execution.assume_role_policy
  # The arithmetic workload has no AWS permissions.
}

resource "aws_ecs_task_definition" "reports" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.task_cpu)
  memory                   = tostring(var.task_memory_mib)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name         = "reports-api"
    image        = var.image_digest_uri
    essential    = true
    command      = ["python", "demo/reporting_api/server.py"]
    environment  = [{ name = "WORKLOAD_HOST", value = "0.0.0.0" }]
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.demo.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "reports"
      }
    }
  }])
  lifecycle {
    precondition {
      condition = contains(lookup({
        "256"  = [512, 1024, 2048], "512" = [1024, 2048, 3072, 4096],
        "1024" = range(2048, 8193, 1024), "2048" = range(4096, 16385, 1024),
        "4096" = range(8192, 30721, 1024)
      }, tostring(var.task_cpu), []), var.task_memory_mib)
      error_message = "Choose a supported Linux Fargate task CPU/memory pair."
    }
  }
}

resource "aws_ecs_service" "demo" {
  name            = "reports-api"
  cluster         = aws_ecs_cluster.demo.id
  task_definition = aws_ecs_task_definition.reports.arn
  launch_type     = "FARGATE"
  desired_count   = var.desired_count
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }
  depends_on = [aws_iam_role_policy.execution]
}

output "collector_scope" {
  value = { region = var.region, cluster = aws_ecs_cluster.demo.name, service = aws_ecs_service.demo.name,
  task_definition_arn = aws_ecs_task_definition.reports.arn, log_group = aws_cloudwatch_log_group.demo.name }
}
