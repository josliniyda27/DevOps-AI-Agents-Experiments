variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "t3.small (2 GB RAM) is the smallest size we would trust. t3.micro (1 GB) may work with the swap file but is a gamble."
  type        = string
  default     = "t3.small"
}

# SSH is optional and off by default: the pipeline deploys through AWS Systems Manager, and
# "aws ssm start-session --target <instance_id>" gives a shell without any open port.
variable "ssh_public_key" {
  description = "Optional. Contents of your SSH public key (cat ~/.ssh/id_ed25519.pub). Empty: no key pair."
  type        = string
  default     = ""
}

variable "ssh_cidr" {
  description = "Optional. The only address allowed to use SSH, as x.x.x.x/32 (see https://checkip.amazonaws.com). Empty: port 22 stays closed."
  type        = string
  default     = ""

  validation {
    condition     = var.ssh_cidr == "" || (can(cidrhost(var.ssh_cidr, 0)) && var.ssh_cidr != "0.0.0.0/0")
    error_message = "Give your own address as x.x.x.x/32; opening SSH to the whole internet is not allowed here."
  }
}
