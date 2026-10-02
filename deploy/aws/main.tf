# The smallest possible AWS deployment: ONE server (EC2) with a fixed public address. Docker Compose runs the website and the
# API on it; Caddy gets a free HTTPS certificate. No load balancer, CloudFront, ECR, NAT gateway or Secrets Manager.
# The CI/CD pipeline (.github/workflows/ci-cd.yml) applies this and then deploys releases to the server through AWS Systems
# Manager, so no SSH port is needed. See docs/cicd.md (pipeline) and docs/deploy.md (by hand).

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }

  # State lives in S3 (bucket made by deploy/aws/bootstrap). The pipeline passes bucket, key and region with -backend-config;
  # by hand: terraform init -backend-config="bucket=<TF_STATE_BUCKET>" -backend-config="key=knowledge-assistant/terraform.tfstate" -backend-config="region=<region>"
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region
}

# The default VPC and the newest Ubuntu 24.04 LTS image: nothing to create.
data "aws_vpc" "default" {
  default = true
}

data "aws_caller_identity" "current" {}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_security_group" "web" {
  name_prefix = "knowledge-assistant-"
  description = "HTTP/HTTPS for everyone; SSH only from your address, and only if you ask for it"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (redirects to HTTPS, and certificate checks)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  dynamic "ingress" {
    for_each = var.ssh_cidr == "" ? [] : [var.ssh_cidr]
    content {
      description = "SSH from your address only"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Optional: only when an SSH key is given. The pipeline does not need SSH; for a shell use:  aws ssm start-session --target <instance_id>
resource "aws_key_pair" "admin" {
  count           = var.ssh_public_key == "" ? 0 : 1
  key_name_prefix = "knowledge-assistant-"
  public_key      = var.ssh_public_key
}

# The server's own identity: the Systems Manager agent (deploys and shell sessions without SSH), and read access to the
# app's settings in Parameter Store (/knowledge-assistant/*), which the deploy script turns into the .env file.
resource "aws_iam_role" "server" {
  name_prefix = "knowledge-assistant-server-"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "server_ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "server_settings" {
  name = "read-app-settings"
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/knowledge-assistant/*"
    }]
  })
}

resource "aws_iam_instance_profile" "server" {
  name_prefix = "knowledge-assistant-server-"
  role        = aws_iam_role.server.name
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.ssh_public_key == "" ? null : aws_key_pair.admin[0].key_name
  iam_instance_profile   = aws_iam_instance_profile.server.name
  vpc_security_group_ids = [aws_security_group.web.id]
  user_data              = file("${path.module}/user_data.sh")

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  # The Name tag is what the pipeline's deploy permission is scoped to; keep it.
  tags = { Name = "knowledge-assistant" }

  lifecycle {
    # A newer Ubuntu image must not replace the running server on the next apply.
    ignore_changes = [ami]
  }
}

# A fixed address, so the hostname does not change when the server restarts.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
}
