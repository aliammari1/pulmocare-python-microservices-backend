import os
import smtplib
from email.mime.text import MIMEText

from . import logger_service


def send_otp_email(to_email, otp):
    try:
        sender_email = os.getenv("EMAIL_ADDRESS")
        sender_password = os.getenv("EMAIL_PASSWORD")

        logger_service.debug(f"Email configuration - Sender: {sender_email}, Password length: {len(sender_password) if sender_password else 0}")

        if not sender_email or not sender_password:
            logger_service.error("Email configuration missing")
            raise Exception("Email configuration missing")

        msg = MIMEText(
            f"""
        Hello,

        Your OTP code for password reset is: {otp}

        This code will expire in 15 minutes.
        If you did not request this code, please ignore this email.

        Best regards,
        Medicare Team
        """
        )

        msg["Subject"] = "Medicare - Password Reset OTP"
        msg["From"] = sender_email
        msg["To"] = to_email

        try:
            logger_service.debug("Attempting SMTP connection to smtp.gmail.com:465")
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
            logger_service.debug("SMTP connection successful")

            logger_service.debug("Attempting SMTP login")
            smtp.login(sender_email, sender_password)
            logger_service.debug("SMTP login successful")

            logger_service.debug("Sending email")
            smtp.send_message(msg)
            logger_service.debug("Email sent successfully")

            smtp.quit()
            return True

        except smtplib.SMTPAuthenticationError as auth_error:
            logger_service.error(f"SMTP Authentication failed - Details: {auth_error!s}")
            raise Exception("Email authentication failed. Please check your credentials.")

        except smtplib.SMTPException as smtp_error:
            logger_service.error(f"SMTP error occurred: {smtp_error!s}")
            raise Exception(f"Email sending failed: {smtp_error!s}")

        except Exception as e:
            logger_service.error(f"Unexpected SMTP error: {e!s}")
            raise Exception(f"Unexpected error while sending email: {e!s}")

    except Exception as e:
        logger_service.error(f"Email sending error: {e!s}")
        return False
