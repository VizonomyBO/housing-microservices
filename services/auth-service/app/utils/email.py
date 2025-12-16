"""
Email helpers for auth-service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


@dataclass
class SesConfig:
    region: str
    source_email: str
    configuration_set: str | None = None


class EmailClient:
    """Thin SES v2 wrapper for sending transactional emails."""

    def __init__(self, ses_config: SesConfig) -> None:
        self.config = ses_config
        self._client = boto3.client("sesv2", region_name=ses_config.region)

    def send_password_reset_email(
        self, to_email: str, reset_url: str, token: str, user_name: str = ""
    ) -> None:
        """Send a password reset email via SES."""
        subject = "Housing Assessment Diagnostic Platform - Password Reset Request"
        display_name = user_name if user_name else to_email.split("@")[0]

        text_body = (
            "THE WORLD BANK\n"
            "Housing Assessment Diagnostic Platform Password Reset Request\n\n"
            f"Hello {display_name},\n\n"
            "We received a request to reset the password for your account on the "
            "World Bank Housing Assessment Diagnostic platform. If you made this "
            "request, please click the link below to create a new password.\n\n"
            f"Reset Your Password: {reset_url}\n\n"
            "If you did not request this, you can safely ignore this email.\n\n"
            "Best regards,\n"
            "The World Bank Housing Assessment Team"
        )

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #e8eef3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
                    <tr>
                        <td style="padding: 40px 50px;">
                            <!-- Logo -->
                            <table role="presentation" style="width: 100%; margin-bottom: 20px;">
                                <tr>
                                    <td style="text-align: center;">
                                        <img src="https://housing-public-content.s3.us-east-1.amazonaws.com/images/logos/world-bank-logo.png" alt="The World Bank" style="height: 40px; width: auto;">
                                    </td>
                                </tr>
                            </table>

                            <!-- Subtitle -->
                            <table role="presentation" style="width: 100%; margin-bottom: 30px;">
                                <tr>
                                    <td style="text-align: center; color: #5a6a7a; font-size: 14px;">
                                        Housing Assessment Diagnostic Platform Password Reset Request
                                    </td>
                                </tr>
                            </table>

                            <!-- Divider -->
                            <table role="presentation" style="width: 100%; margin-bottom: 30px;">
                                <tr>
                                    <td style="border-bottom: 1px solid #e0e0e0;"></td>
                                </tr>
                            </table>

                            <!-- Content -->
                            <table role="presentation" style="width: 100%;">
                                <tr>
                                    <td style="color: #333333; font-size: 15px; line-height: 1.6;">
                                        <p style="margin: 0 0 20px 0;">Hello {display_name},</p>
                                        <p style="margin: 0 0 30px 0;">
                                            We received a request to reset the password for your account on the
                                            World Bank Housing Assessment Diagnostic platform. If you made this
                                            request, please click the button below to create a new password.
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <!-- Button -->
                            <table role="presentation" style="width: 100%; margin-bottom: 30px;">
                                <tr>
                                    <td style="text-align: center;">
                                        <a href="{reset_url}" style="display: inline-block; background-color: #f5c242; color: #1a1a1a; text-decoration: none; padding: 14px 40px; border-radius: 6px; font-size: 15px; font-weight: 500; width: 80%; text-align: center;">
                                            Reset Your Password
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <!-- Footer note -->
                            <table role="presentation" style="width: 100%;">
                                <tr>
                                    <td style="color: #666666; font-size: 13px; line-height: 1.5;">
                                        <p style="margin: 0;">If you did not request this, you can safely ignore this email.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """

        message = {
            "FromEmailAddress": self.config.source_email,
            "Destination": {"ToAddresses": [to_email]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                }
            },
        }

        if self.config.configuration_set:
            message["ConfigurationSetName"] = self.config.configuration_set

        try:
            self._client.send_email(**message)
            logger.info(
                "Password reset email sent via SES",
                extra={"to": to_email, "config_set": self.config.configuration_set},
            )
        except (ClientError, BotoCoreError):
            logger.exception(
                "Failed to send password reset email via SES",
                extra={"to": to_email},
            )
            raise
