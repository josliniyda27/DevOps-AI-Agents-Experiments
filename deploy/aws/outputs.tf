output "public_ip" {
  value = aws_eip.app.public_ip
}

output "site_address" {
  description = "Free hostname that points at the server; use it as SITE_ADDRESS in .env to get HTTPS without buying a domain"
  value       = "${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
}

output "ssh" {
  value = "ssh ubuntu@${aws_eip.app.public_ip}"
}
