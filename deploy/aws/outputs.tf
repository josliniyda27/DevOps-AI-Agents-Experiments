output "public_ip" {
  value = aws_eip.app.public_ip
}

output "site_address" {
  description = "Free hostname that points at the server; the pipeline uses it as SITE_ADDRESS, so Caddy gets an HTTPS certificate without a domain"
  value       = "${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
}

output "instance_id" {
  description = "The pipeline deploys to this server through AWS Systems Manager"
  value       = aws_instance.app.id
}

output "shell" {
  description = "A shell on the server without SSH"
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.app.id}"
}

output "ssh" {
  value = var.ssh_public_key == "" ? "SSH is off (no ssh_public_key given)" : "ssh ubuntu@${aws_eip.app.public_ip}"
}
