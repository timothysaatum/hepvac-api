"""
Notification Service

Provides unified interface for sending emails and SMS notifications.
Supports multiple providers and includes template rendering.
"""
import aiosmtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
from jinja2 import Template
from pathlib import Path

from app.core.utils import logger
from app.config.config import settings


class EmailConfig:
    """Email configuration."""

    SMTP_HOST: str = getattr(settings, "SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = getattr(settings, "SMTP_PORT", 587)
    SMTP_USER: str = getattr(settings, "SMTP_USER", "")
    SMTP_PASSWORD: str = getattr(settings, "SMTP_PASSWORD", "")
    FROM_EMAIL: str = getattr(settings, "FROM_EMAIL", "timothysaatum@gmail.com")
    FROM_NAME: str = getattr(settings, "FROM_NAME", "Your App")


class SMSConfig:
    """SMS configuration."""

    # Twilio
    AFRICAISTALKING: str = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    AFRICAISTALKING_AUTH_TOKEN: str = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    AFRICAISTALKING_PHONE_NUMBER: str = getattr(settings, "TWILIO_PHONE_NUMBER", "")

    # Termii (Alternative)
    TERMII_API_KEY: str = getattr(settings, "TERMII_API_KEY", "")
    TERMII_SENDER_ID: str = getattr(settings, "TERMII_SENDER_ID", "")

    # Default provider: 'twilio' or 'termii'
    SMS_PROVIDER: str = getattr(settings, "SMS_PROVIDER", "twilio")


class EmailService:
    """Service for sending emails."""

    @staticmethod
    async def send_email(
        to: str | List[str],
        subject: str,
        body: str,
        html: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Send email using SMTP.

        Args:
            to: Recipient email(s)
            subject: Email subject
            body: Plain text body
            html: HTML body (optional)
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            attachments: List of attachment dicts with 'filename' and 'content'

        Returns:
            bool: True if sent successfully

        Example:
            >>> await EmailService.send_email(
            ...     to="user@example.com",
            ...     subject="Welcome!",
            ...     body="Welcome to our platform",
            ...     html="<h1>Welcome!</h1><p>Welcome to our platform</p>"
            ... )
        """
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{EmailConfig.FROM_NAME} <{EmailConfig.FROM_EMAIL}>"

            # Handle multiple recipients
            if isinstance(to, str):
                to = [to]
            message["To"] = ", ".join(to)

            if cc:
                message["Cc"] = ", ".join(cc)

            # Attach text and HTML parts
            message.attach(MIMEText(body, "plain"))
            if html:
                message.attach(MIMEText(html, "html"))

            # Send email
            await aiosmtplib.send(
                message,
                hostname=EmailConfig.SMTP_HOST,
                port=EmailConfig.SMTP_PORT,
                username=EmailConfig.SMTP_USER,
                password=EmailConfig.SMTP_PASSWORD,
                start_tls=True,
            )

            logger.log_info(
                {
                    "event_type": "email_sent",
                    "to": to,
                    "subject": subject,
                }
            )

            return True

        except Exception as e:
            logger.log_error(
                {
                    "event_type": "email_send_failed",
                    "to": to,
                    "subject": subject,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            return False

    @staticmethod
    async def send_template_email(
        to: str | List[str],
        subject: str,
        template_name: str,
        context: Dict[str, Any],
        **kwargs,
    ) -> bool:
        """
        Send email using a template.

        Args:
            to: Recipient email(s)
            subject: Email subject
            template_name: Template filename (without .html/.txt)
            context: Template context variables
            **kwargs: Additional arguments for send_email

        Returns:
            bool: True if sent successfully

        Example:
            >>> await EmailService.send_template_email(
            ...     to="user@example.com",
            ...     subject="Welcome!",
            ...     template_name="welcome",
            ...     context={"username": "John", "activation_link": "..."}
            ... )
        """
        try:
            # Load templates
            template_dir = Path(__file__).parent.parent / "templates" / "emails"

            # Try to load HTML template
            html_path = template_dir / f"{template_name}.html"
            html = None
            if html_path.exists():
                html_template = Template(html_path.read_text())
                html = html_template.render(**context)

            # Try to load text template
            txt_path = template_dir / f"{template_name}.txt"
            if txt_path.exists():
                txt_template = Template(txt_path.read_text())
                body = txt_template.render(**context)
            else:
                # Fallback to plain text from HTML
                body = context.get("message", "")

            return await EmailService.send_email(
                to=to, subject=subject, body=body, html=html, **kwargs
            )

        except Exception as e:
            logger.log_error(
                {
                    "event_type": "template_email_failed",
                    "template": template_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False


class SMSService:
    """Service for sending SMS notifications."""

    @staticmethod
    async def send_sms_twilio(to: str, message: str) -> bool:
        """Send SMS using Africa is Taling."""
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{SMSConfig.AFRICAISTALKING}/Messages.json"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    auth=(SMSConfig.AFRICAISTALKING_AUTH_TOKEN, SMSConfig.AFRICAISTALKING_AUTH_TOKEN),
                    data={
                        "From": SMSConfig.AFRICAISTALKING_PHONE_NUMBER,
                        "To": to,
                        "Body": message,
                    },
                )

                if response.status_code == 201:
                    logger.log_info(
                        {
                            "event_type": "sms_sent",
                            "provider": "twilio",
                            "to": to,
                        }
                    )
                    return True
                else:
                    logger.log_error(
                        {
                            "event_type": "sms_send_failed",
                            "provider": "twilio",
                            "to": to,
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
                    return False

        except Exception as e:
            logger.log_error(
                {
                    "event_type": "sms_send_error",
                    "provider": "twilio",
                    "to": to,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False

    @staticmethod
    async def send_sms_termii(to: str, message: str) -> bool:
        """Send SMS using Termii (African SMS provider)."""
        try:
            url = "https://api.ng.termii.com/api/sms/send"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={
                        "to": to,
                        "from": SMSConfig.TERMII_SENDER_ID,
                        "sms": message,
                        "type": "plain",
                        "channel": "generic",
                        "api_key": SMSConfig.TERMII_API_KEY,
                    },
                )

                if response.status_code == 200:
                    logger.log_info(
                        {
                            "event_type": "sms_sent",
                            "provider": "termii",
                            "to": to,
                        }
                    )
                    return True
                else:
                    logger.log_error(
                        {
                            "event_type": "sms_send_failed",
                            "provider": "termii",
                            "to": to,
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
                    return False

        except Exception as e:
            logger.log_error(
                {
                    "event_type": "sms_send_error",
                    "provider": "termii",
                    "to": to,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False

    @staticmethod
    async def send_sms(
        to: str | List[str], message: str, provider: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Send SMS using configured provider.

        Args:
            to: Recipient phone number(s) in E.164 format (+1234567890)
            message: SMS message text
            provider: Override default provider ('twilio' or 'termii')

        Returns:
            Dict mapping phone numbers to success status

        Example:
            >>> await SMSService.send_sms(
            ...     to="+1234567890",
            ...     message="Your verification code is: 123456"
            ... )
        """
        provider = provider or SMSConfig.SMS_PROVIDER

        # Handle multiple recipients
        if isinstance(to, str):
            to = [to]

        results = {}
        for phone in to:
            if provider == "twilio":
                success = await SMSService.send_sms_twilio(phone, message)
            elif provider == "termii":
                success = await SMSService.send_sms_termii(phone, message)
            else:
                logger.log_error(
                    {
                        "event_type": "invalid_sms_provider",
                        "provider": provider,
                    }
                )
                success = False

            results[phone] = success

        return results


class NotificationService:
    """Unified notification service for email and SMS."""

    @staticmethod
    async def send_welcome_email(
        email: str, username: str, activation_link: Optional[str] = None
    ) -> bool:
        """Send welcome email to new user."""
        context = {
            "username": username,
            "activation_link": activation_link,
        }

        return await EmailService.send_template_email(
            to=email,
            subject="Welcome to Our Platform!",
            template_name="welcome",
            context=context,
        )

    @staticmethod
    async def send_password_reset_email(
        email: str, username: str, reset_link: str
    ) -> bool:
        """Send password reset email."""
        context = {
            "username": username,
            "reset_link": reset_link,
        }

        return await EmailService.send_template_email(
            to=email,
            subject="Password Reset Request",
            template_name="password_reset",
            context=context,
        )

    @staticmethod
    async def send_verification_code_sms(phone: str, code: str) -> bool:
        """Send verification code via SMS."""
        message = f"Your verification code is: {code}. Valid for 10 minutes."
        result = await SMSService.send_sms(phone, message)
        return result.get(phone, False)

    @staticmethod
    async def send_alert(
        email: Optional[str] = None,
        phone: Optional[str] = None,
        subject: str = None,
        message: str = None,
    ) -> Dict[str, bool]:
        """
        Send alert via both email and SMS.

        Returns:
            Dict with 'email' and 'sms' keys indicating success
        """
        results = {}

        if email and message:
            results["email"] = await EmailService.send_email(
                to=email,
                subject=subject or "Alert",
                body=message,
            )

        if phone and message:
            sms_results = await SMSService.send_sms(phone, message)
            results["sms"] = sms_results.get(phone, False)

        return results
