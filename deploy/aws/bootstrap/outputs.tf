# Copy these into the repository's GitHub variables (Settings, Secrets and variables, Actions, Variables).

output "AWS_ROLE_ARN" {
  value = aws_iam_role.deployer.arn
}

output "TF_STATE_BUCKET" {
  value = aws_s3_bucket.state.bucket
}

output "AWS_REGION" {
  value = var.region
}
