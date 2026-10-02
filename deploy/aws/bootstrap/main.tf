# Run ONCE from your own machine, with your own AWS credentials, before the pipeline's first run (see docs/cicd.md):
#   cd deploy/aws/bootstrap && terraform init && terraform apply -var github_repo=<owner>/<repo>
#
# It creates the three things the pipeline cannot create for itself:
#   1. an S3 bucket for the pipeline's Terraform state (versioned, encrypted, private; locking uses an S3 lock file),
#   2. trust between AWS and GitHub Actions (OIDC), so the pipeline needs no stored AWS keys,
#   3. the role the pipeline assumes, allowed only what deploy/aws needs, and only from this repository's
#      "production" GitHub environment.
# This folder keeps its own state locally (terraform.tfstate here, git-ignored). Keep that file.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  state_bucket = "knowledge-assistant-tfstate-${local.account_id}"
  oidc_url     = "token.actions.githubusercontent.com"
  oidc_arn     = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${local.account_id}:oidc-provider/${local.oidc_url}"
}

# ---- 1. Terraform state bucket

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---- 2. GitHub Actions OIDC (an account can have only one; set create_oidc_provider=false if it already exists)

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = "https://${local.oidc_url}"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

# ---- 3. The pipeline's role

resource "aws_iam_role" "deployer" {
  name        = "knowledge-assistant-github-deployer"
  description = "Assumed by GitHub Actions (${var.github_repo}, environment ${var.github_environment}) to run deploy/aws and deploy releases"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_url}:aud" = "sts.amazonaws.com"
          "${local.oidc_url}:sub" = "repo:${var.github_repo}:environment:${var.github_environment}"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "deployer" {
  name = "deploy-knowledge-assistant"
  role = aws_iam_role.deployer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "TerraformState"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.state.arn
      },
      {
        Sid      = "TerraformStateObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.state.arn}/*"
      },
      {
        # The server, its security group, key pair and Elastic IP; only in the chosen region.
        Sid       = "Ec2InRegion"
        Effect    = "Allow"
        Action    = ["ec2:*"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = var.region } }
      },
      {
        Sid    = "ServerRole"
        Effect = "Allow"
        Action = [
          "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy",
          "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole",
          "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:PassRole",
          "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile", "iam:TagInstanceProfile",
          "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
        ]
        Resource = [
          "arn:aws:iam::${local.account_id}:role/knowledge-assistant-server*",
          "arn:aws:iam::${local.account_id}:instance-profile/knowledge-assistant-server*",
        ]
      },
      {
        # The server role may only ever receive the Systems Manager agent's managed policy.
        Sid       = "ServerRoleManagedPolicy"
        Effect    = "Allow"
        Action    = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
        Resource  = "arn:aws:iam::${local.account_id}:role/knowledge-assistant-server*"
        Condition = { ArnEquals = { "iam:PolicyARN" = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" } }
      },
      {
        Sid      = "AppSettings"
        Effect   = "Allow"
        Action   = ["ssm:PutParameter", "ssm:GetParameter", "ssm:DeleteParameter", "ssm:AddTagsToResource"]
        Resource = "arn:aws:ssm:${var.region}:${local.account_id}:parameter/knowledge-assistant/*"
      },
      {
        # Deploy releases with Run Command: only on the app server (tagged Name=knowledge-assistant) ...
        Sid       = "RunDeployCommandOnServer"
        Effect    = "Allow"
        Action    = ["ssm:SendCommand"]
        Resource  = "arn:aws:ec2:${var.region}:${local.account_id}:instance/*"
        Condition = { StringEquals = { "ssm:resourceTag/Name" = "knowledge-assistant" } }
      },
      {
        # ... and only with the stock shell-script document.
        Sid      = "RunDeployCommandDocument"
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = "arn:aws:ssm:${var.region}::document/AWS-RunShellScript"
      },
      {
        Sid      = "WatchDeployCommand"
        Effect   = "Allow"
        Action   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ssm:DescribeInstanceInformation"]
        Resource = "*"
      },
    ]
  })
}
