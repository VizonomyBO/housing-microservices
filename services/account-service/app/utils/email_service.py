"""
Email service using AWS SES
"""

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app

from app.config import Config


class EmailService:
    """Service for sending emails via AWS SES"""

    @staticmethod
    def send_email(
        to: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_email: str | None = None,
    ) -> tuple[bool, str]:
        """
        Send an email using AWS SES.

        Args:
            to: Recipient email address
            subject: Email subject
            body_text: Plain text email body
            body_html: HTML email body (optional)
            from_email: Sender email address (defaults to EMAIL_FROM config)

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Get AWS credentials from environment
            aws_access_key_id = current_app.config.get("AWS_ACCESS_KEY_ID")
            aws_secret_access_key = current_app.config.get("AWS_SECRET_ACCESS_KEY")
            aws_region = current_app.config.get("AWS_REGION", "us-east-1")
            from_email = from_email or current_app.config.get("EMAIL_FROM", "noreply@example.com")

            if not aws_access_key_id or not aws_secret_access_key:
                return False, "AWS credentials not configured"

            # Create SES client
            ses_client = boto3.client(
                "ses",
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=aws_region,
            )

            # Prepare email message
            destination = {"ToAddresses": [to]}

            message = {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text, "Charset": "UTF-8"},
                },
            }

            # Add HTML body if provided
            if body_html:
                message["Body"]["Html"] = {"Data": body_html, "Charset": "UTF-8"}

            # Send email
            response = ses_client.send_email(
                Source=from_email,
                Destination=destination,
                Message=message,
            )

            message_id = response.get("MessageId", "")
            return True, f"Email sent successfully (MessageId: {message_id})"

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            return False, f"AWS SES error ({error_code}): {error_message}"

        except BotoCoreError as e:
            return False, f"AWS SDK error: {str(e)}"

        except Exception as e:
            return False, f"Unexpected error sending email: {str(e)}"

    @staticmethod
    def send_password_reset_email(to: str, reset_token: str, reset_url: str | None = None) -> tuple[bool, str]:
        """
        Send a password reset email.

        Args:
            to: Recipient email address
            reset_token: Password reset token
            reset_url: Optional full reset URL (if not provided, token will be included in email)

        Returns:
            Tuple of (success: bool, message: str)
        """
        subject = "Password Reset Request"

        # Build reset URL
        if reset_url:
            reset_link = reset_url
        else:
            # Default reset URL format (frontend should handle this)
            reset_link = f"https://yourdomain.com/reset-password?token={reset_token}"

        # Plain text version
        body_text = f"""
Password Reset Request

You have requested to reset your password. Please use the following token or link:

Token: {reset_token}

Or click this link: {reset_link}

This token will expire in 1 hour.

If you did not request this password reset, please ignore this email.

Best regards,
Account Management Service
"""

        # HTML version
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9f9f9; }}
        .token {{ background-color: #fff; padding: 15px; border: 2px solid #4CAF50; border-radius: 5px; font-family: monospace; font-size: 18px; text-align: center; margin: 20px 0; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Password Reset Request</h1>
        </div>
        <div class="content">
            <p>You have requested to reset your password.</p>
            <p>Please use the following token:</p>
            <div class="token">{reset_token}</div>
            <p>Or click the button below to reset your password:</p>
            <a href="{reset_link}" class="button">Reset Password</a>
            <p><strong>This token will expire in 1 hour.</strong></p>
            <p>If you did not request this password reset, please ignore this email.</p>
        </div>
        <div class="footer">
            <p>Best regards,<br>Account Management Service</p>
        </div>
    </div>
</body>
</html>
"""

        return EmailService.send_email(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

