variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Set the exact dedicated demo account ID."
  }
}
variable "name" {
  type    = string
  default = "proofops-demo-isolated"
  validation {
    condition     = can(regex("^proofops-demo-[a-z0-9-]{3,24}$", var.name))
    error_message = "Use a distinct proofops-demo- name in a dedicated environment."
  }
}
variable "image_digest_uri" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-zA-Z0-9._/-]+@sha256:[a-f0-9]{64}$", var.image_digest_uri))
    error_message = "Supply a tested Linux x86_64 ECR image pinned by digest."
  }
}
variable "ecr_repository_arn" {
  type = string
}
variable "private_subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.private_subnet_ids) > 0
    error_message = "Use explicitly reviewed private subnets with required ECR/log egress."
  }
}
variable "security_group_ids" {
  type = list(string)
  validation {
    condition     = length(var.security_group_ids) > 0
    error_message = "Supply security groups limited to the intended test generator."
  }
}
variable "task_cpu" {
  type    = number
  default = 1024
}
variable "task_memory_mib" {
  type    = number
  default = 2048
}
variable "desired_count" {
  type    = number
  default = 0
  validation {
    condition     = contains([0, 1], var.desired_count)
    error_message = "This isolated demo permits zero or one running task only."
  }
}
