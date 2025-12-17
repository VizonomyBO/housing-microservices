locals {
  ses_enabled      = var.ses_domain != "" || var.ses_from_email != ""
  ses_identity_arn = var.ses_domain != "" ? "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_domain}" : null
}

resource "aws_ses_domain_identity" "ses_domain" {
  count  = var.ses_domain != "" ? 1 : 0
  domain = var.ses_domain
}

resource "aws_ses_domain_dkim" "ses_domain" {
  count  = var.ses_domain != "" ? 1 : 0
  domain = aws_ses_domain_identity.ses_domain[0].domain
}

resource "aws_sesv2_configuration_set" "default" {
  count = var.ses_configuration_set_name != "" ? 1 : 0

  configuration_set_name = var.ses_configuration_set_name

  delivery_options {
    tls_policy = "OPTIONAL"
  }
}

# =============================================================================
# Email Identity Verification (required for SES sandbox mode)
# Both sender and recipient must be verified in sandbox mode
# =============================================================================

resource "aws_sesv2_email_identity" "sender" {
  count = local.ses_enabled ? 1 : 0

  email_identity = "addis@vizonomy.com"
}

resource "aws_sesv2_email_identity" "test_recipient" {
  count = local.ses_enabled ? 1 : 0

  email_identity = "xdaddisxd@gmail.com"
}

resource "aws_iam_policy" "ses_send_email" {
  count = local.ses_enabled ? 1 : 0

  name        = "${var.project_name}-ses-send-${var.environment}"
  description = "Allow microservices to send email via SES"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = local.ses_identity_arn != null ? [local.ses_identity_arn] : ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_ses_send" {
  count      = local.ses_enabled ? 1 : 0
  role       = aws_iam_role.ec2_microservices.name
  policy_arn = aws_iam_policy.ses_send_email[0].arn
}

output "ses_verification_token" {
  description = "SES domain verification token (add as TXT record)"
  value       = var.ses_domain != "" ? aws_ses_domain_identity.ses_domain[0].verification_token : ""
}

output "ses_dkim_tokens" {
  description = "SES DKIM tokens (add as CNAME records)"
  value       = var.ses_domain != "" ? aws_ses_domain_dkim.ses_domain[0].dkim_tokens : []
}
