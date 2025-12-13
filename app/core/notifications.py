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
    FROM_EMAIL: str = getattr(settings, "FROM_EMAIL", "noreply@healthapp.com")
    FROM_NAME: str = getattr(settings, "FROM_NAME", "Health App")


class SMSConfig:
    """SMS configuration."""

    # Termii (Primary for Ghana)
    TERMII_API_KEY: str = getattr(settings, "TERMII_API_KEY", "")
    TERMII_SENDER_ID: str = getattr(settings, "TERMII_SENDER_ID", "HealthApp")

    # Default provider: 'termii', 'twilio', or 'mock'
    SMS_PROVIDER: str = getattr(settings, "SMS_PROVIDER", "termii")


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
    def _format_phone_number(phone: str, provider: str = "termii") -> str:
        """Format phone number for the specific provider."""
        # Remove spaces and special characters
        phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        # Handle Ghana numbers (starting with 0)
        if phone.startswith("0"):
            phone = "233" + phone[1:]  # Ghana country code
        
        # Remove + for Termii, keep it for Twilio
        if provider == "termii":
            return phone.replace("+", "")
        else:  # twilio
            if not phone.startswith("+"):
                phone = "+" + phone
            return phone

    @staticmethod
    async def send_sms_termii(to: str, message: str) -> Dict[str, Any]:
        """
        Send SMS using Termii (African SMS provider - best for Ghana).
        
        Returns:
            Dict with 'success', 'message_id', and optional 'error' keys
        """
        try:
            # Format phone number (without +)
            formatted_phone = SMSService._format_phone_number(to, provider="termii")
            
            url = "https://api.ng.termii.com/api/sms/send"
            print(f"========={url}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={
                        "to": formatted_phone,
                        "from": SMSConfig.TERMII_SENDER_ID,
                        "sms": message,
                        "type": "plain",
                        "channel": "generic",
                        "api_key": SMSConfig.TERMII_API_KEY,
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.log_info(
                        {
                            "event_type": "sms_sent",
                            "provider": "termii",
                            "to": formatted_phone,
                            "message_id": data.get("message_id"),
                        }
                    )
                    return {
                        "success": True,
                        "message_id": data.get("message_id"),
                        "balance": data.get("balance"),
                        "to": formatted_phone,
                    }
                else:
                    error_msg = f"Status {response.status_code}: {response.text}"
                    logger.log_error(
                        {
                            "event_type": "sms_send_failed",
                            "provider": "termii",
                            "to": formatted_phone,
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
                    return {
                        "success": False,
                        "error": error_msg,
                        "to": formatted_phone,
                    }

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
            return {
                "success": False,
                "error": str(e),
                "to": to,
            }

    @staticmethod
    async def send_sms_mock(to: str, message: str) -> Dict[str, Any]:
        """Mock SMS sending for testing."""
        formatted_phone = SMSService._format_phone_number(to)
        
        print(f"\n{'='*60}")
        print(f"[MOCK SMS SENT]")
        print(f"To: {formatted_phone}")
        print(f"Message: {message}")
        print(f"{'='*60}\n")
        
        logger.log_info(
            {
                "event_type": "sms_sent",
                "provider": "mock",
                "to": formatted_phone,
            }
        )
        
        return {
            "success": True,
            "message_id": f"mock_{hash(formatted_phone + message)}",
            "to": formatted_phone,
        }

    @staticmethod
    async def send_sms(
        to: str | List[str], 
        message: str, 
        provider: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Send SMS using configured provider.

        Args:
            to: Recipient phone number(s) in any format
            message: SMS message text (max 160 chars for single SMS)
            provider: Override default provider ('termii', 'twilio', or 'mock')

        Returns:
            Dict mapping phone numbers to result dicts with 'success', 'message_id', etc.

        Example:
            >>> results = await SMSService.send_sms(
            ...     to="0501234567",
            ...     message="Your appointment is tomorrow at 10 AM"
            ... )
            >>> print(results["233501234567"]["success"])  # True
        """
        provider = provider or SMSConfig.SMS_PROVIDER

        # Handle multiple recipients
        if isinstance(to, str):
            to = [to]

        results = {}
        for phone in to:
            if provider == "termii":
                result = await SMSService.send_sms_termii(phone, message)
            elif provider == "mock":
                result = await SMSService.send_sms_mock(phone, message)
            else:
                logger.log_error(
                    {
                        "event_type": "invalid_sms_provider",
                        "provider": provider,
                    }
                )
                result = {
                    "success": False,
                    "error": f"Invalid SMS provider: {provider}",
                    "to": phone,
                }

            # Use the formatted phone number as key
            results[result["to"]] = result

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
        results = await SMSService.send_sms(phone, message)
        
        # Get result for the formatted phone number
        for result in results.values():
            return result.get("success", False)
        
        return False

    @staticmethod
    async def send_patient_reminder(
        phone: str, 
        patient_name: str,
        reminder_message: str
    ) -> Dict[str, Any]:
        """
        Send reminder to patient via SMS.
        
        Returns:
            Dict with 'success', 'message_id', and optional 'error' keys
        """
        # Personalize message
        message = reminder_message.replace("{name}", patient_name)
        
        results = await SMSService.send_sms(phone, message)
        
        # Return first (and should be only) result
        for result in results.values():
            return result
        
        return {"success": False, "error": "No results returned"}

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
            # Get first result
            for result in sms_results.values():
                results["sms"] = result.get("success", False)
                break

        return results