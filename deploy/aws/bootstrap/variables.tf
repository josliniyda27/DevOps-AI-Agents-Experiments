variable "github_repo" {
  description = "The GitHub repository allowed to deploy, as owner/name (for example josliniyda27/DevOps-AI-Agents-Experiments)"
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repo))
    error_message = "Write it as owner/name."
  }
}

variable "github_environment" {
  description = "The GitHub environment whose jobs may assume the role. The pipeline's AWS jobs run in it."
  type        = string
  default     = "production"
}

variable "region" {
  description = "AWS region; must match AWS_REGION in the repository's GitHub variables"
  type        = string
  default     = "ap-south-1"
}

variable "create_oidc_provider" {
  description = "false if this AWS account already trusts GitHub Actions (IAM, Identity providers, token.actions.githubusercontent.com)"
  type        = bool
  default     = true
}
