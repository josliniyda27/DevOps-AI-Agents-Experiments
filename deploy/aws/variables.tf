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

variable "ssh_public_key" {
  description = "Contents of your SSH public key, for example the output of: cat ~/.ssh/id_ed25519.pub"
  type        = string
}

variable "ssh_cidr" {
  description = "The only address allowed to use SSH, written as x.x.x.x/32 (look yours up at https://checkip.amazonaws.com)"
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_cidr, 0)) && var.ssh_cidr != "0.0.0.0/0"
    error_message = "Give your own address as x.x.x.x/32; opening SSH to the whole internet is not allowed here."
  }
}
