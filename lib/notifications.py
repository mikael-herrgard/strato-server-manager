"""
Notification Manager
Handles email notifications for automated tasks
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
from .utils import logger
from .config import get_config


class NotificationManager:
    """Manages email notifications"""

    def __init__(self):
        """Initialize notification manager"""
        self.config = get_config()
        self.notification_config = self._load_notification_config()
        logger.info("NotificationManager initialized")

    def _load_notification_config(self) -> Dict:
        """
        Load notification configuration

        Returns:
            Notification configuration dictionary
        """
        config_file = Path("/opt/server-manager/config/notifications.yaml")

        if not config_file.exists():
            # Return default config
            return {
                'enabled': False,
                'smtp_server': 'localhost',
                'smtp_port': 25,
                'smtp_use_tls': False,
                'smtp_user': '',
                'smtp_password': '',
                'from_email': 'server-manager@localhost',
                'to_emails': [],
                'notify_on_success': False,
                'notify_on_failure': True
            }

        try:
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            return config.get('notifications', {})
        except Exception as e:
            logger.error(f"Failed to load notification config: {e}")
            return {
                'enabled': False,
                'from_email': 'server-manager@localhost',
                'to_emails': []
            }

    def save_notification_config(self, config: Dict) -> bool:
        """
        Save notification configuration

        Args:
            config: Configuration dictionary

        Returns:
            True if saved successfully
        """
        try:
            config_file = Path("/opt/server-manager/config/notifications.yaml")
            config_file.parent.mkdir(parents=True, exist_ok=True)

            import yaml
            with open(config_file, 'w') as f:
                yaml.dump({'notifications': config}, f, default_flow_style=False)

            self.notification_config = config
            logger.info("Notification config saved")
            return True

        except Exception as e:
            logger.error(f"Failed to save notification config: {e}")
            return False

    def is_configured(self) -> bool:
        """
        Check if notifications are configured

        Returns:
            True if configured and enabled
        """
        return (
            self.notification_config.get('enabled', False) and
            bool(self.notification_config.get('to_emails', []))
        )

    def send_backup_notification(
        self,
        service: str,
        success: bool,
        details: Dict
    ) -> bool:
        """
        Send backup completion notification

        Args:
            service: Service name that was backed up
            success: Whether backup succeeded
            details: Backup details dictionary

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            return False

        # Check if we should notify
        if success and not self.notification_config.get('notify_on_success', False):
            return False
        if not success and not self.notification_config.get('notify_on_failure', True):
            return False

        try:
            subject = self._build_backup_subject(service, success)
            body = self._build_backup_body(service, success, details)

            return self._send_email(subject, body)

        except Exception as e:
            logger.error(f"Failed to send backup notification: {e}")
            return False

    def _build_backup_subject(self, service: str, success: bool) -> str:
        """Build email subject for backup notification"""
        status = "SUCCESS" if success else "FAILED"
        hostname = os.uname().nodename
        return f"[{status}] Backup: {service} on {hostname}"

    def _build_backup_body(self, service: str, success: bool, details: Dict) -> str:
        """Build email body for backup notification"""
        hostname = os.uname().nodename
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if success:
            body = f"""Backup Successful

Server: {hostname}
Service: {service}
Time: {timestamp}
Status: SUCCESS

Details:
"""
            if 'backup_path' in details:
                body += f"  Backup Path: {details['backup_path']}\n"
            if 'size' in details:
                body += f"  Size: {details['size']}\n"
            if 'duration' in details:
                body += f"  Duration: {details['duration']}\n"
            if 'verified' in details:
                body += f"  Verified: {details['verified']}\n"

        else:
            body = f"""Backup Failed

Server: {hostname}
Service: {service}
Time: {timestamp}
Status: FAILED

Error Details:
"""
            if 'error' in details:
                body += f"  Error: {details['error']}\n"
            if 'output' in details:
                body += f"\nOutput:\n{details['output']}\n"

        body += f"""

---
This is an automated notification from server-manager
Server Manager v1.0
"""

        return body

    def send_maintenance_notification(
        self,
        task: str,
        success: bool,
        details: Dict
    ) -> bool:
        """
        Send maintenance task notification

        Args:
            task: Maintenance task name
            success: Whether task succeeded
            details: Task details dictionary

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            return False

        if success and not self.notification_config.get('notify_on_success', False):
            return False
        if not success and not self.notification_config.get('notify_on_failure', True):
            return False

        try:
            hostname = os.uname().nodename
            status = "SUCCESS" if success else "FAILED"

            subject = f"[{status}] Maintenance: {task} on {hostname}"

            body = f"""Maintenance Task {status}

Server: {hostname}
Task: {task}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Status: {status}

Details:
"""
            for key, value in details.items():
                body += f"  {key}: {value}\n"

            body += """

---
This is an automated notification from server-manager
Server Manager v1.0
"""

            return self._send_email(subject, body)

        except Exception as e:
            logger.error(f"Failed to send maintenance notification: {e}")
            return False

    def send_health_check_notification(
        self,
        status: Dict,
        issues: List[str]
    ) -> bool:
        """
        Send health check notification

        Args:
            status: Health check status dictionary
            issues: List of detected issues

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            return False

        # Only send if there are issues
        if not issues and not self.notification_config.get('notify_on_success', False):
            return False

        try:
            hostname = os.uname().nodename
            severity = "WARNING" if issues else "OK"

            subject = f"[{severity}] Health Check: {hostname}"

            body = f"""Health Check Report

Server: {hostname}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Status: {severity}

"""
            if issues:
                body += "Issues Detected:\n"
                for issue in issues:
                    body += f"  • {issue}\n"
                body += "\n"

            body += "Service Status:\n"
            for service, info in status.items():
                body += f"  {service}: {info}\n"

            body += """

---
This is an automated notification from server-manager
Server Manager v1.0
"""

            return self._send_email(subject, body)

        except Exception as e:
            logger.error(f"Failed to send health check notification: {e}")
            return False

    def send_custom_notification(
        self,
        subject: str,
        message: str,
        level: str = "INFO"
    ) -> bool:
        """
        Send custom notification

        Args:
            subject: Email subject
            message: Email message
            level: Notification level (INFO, WARNING, ERROR)

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            return False

        try:
            hostname = os.uname().nodename
            full_subject = f"[{level}] {subject} - {hostname}"

            body = f"""{message}

---
Server: {hostname}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Level: {level}

This is an automated notification from server-manager
Server Manager v1.0
"""

            return self._send_email(full_subject, body)

        except Exception as e:
            logger.error(f"Failed to send custom notification: {e}")
            return False

    def _send_email(self, subject: str, body: str) -> bool:
        """
        Send email via SMTP

        Args:
            subject: Email subject
            body: Email body

        Returns:
            True if sent successfully
        """
        try:
            smtp_server = self.notification_config.get('smtp_server', 'localhost')
            smtp_port = self.notification_config.get('smtp_port', 25)
            use_tls = self.notification_config.get('smtp_use_tls', False)
            smtp_user = self.notification_config.get('smtp_user', '')
            smtp_password = self.notification_config.get('smtp_password', '')
            from_email = self.notification_config.get('from_email', 'server-manager@localhost')
            to_emails = self.notification_config.get('to_emails', [])

            if not to_emails:
                logger.warning("No recipient emails configured")
                return False

            # Create message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            # Send via SMTP
            if use_tls:
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    server.send_message(msg)

            logger.info(f"Email notification sent to {', '.join(to_emails)}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def test_notification(self) -> Dict[str, any]:
        """
        Send test notification

        Returns:
            Test result dictionary
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Notifications not configured'
            }

        try:
            hostname = os.uname().nodename
            subject = f"[TEST] Server Manager Notification Test - {hostname}"

            body = f"""This is a test notification from Server Manager.

Server: {hostname}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

If you receive this email, notifications are working correctly!

Configuration:
  SMTP Server: {self.notification_config.get('smtp_server')}
  SMTP Port: {self.notification_config.get('smtp_port')}
  From: {self.notification_config.get('from_email')}
  To: {', '.join(self.notification_config.get('to_emails', []))}

---
Server Manager v1.0
"""

            success = self._send_email(subject, body)

            return {
                'success': success,
                'error': None if success else 'Failed to send test email'
            }

        except Exception as e:
            logger.error(f"Test notification failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_notification_status(self) -> Dict[str, any]:
        """
        Get notification system status

        Returns:
            Status dictionary
        """
        return {
            'configured': self.is_configured(),
            'enabled': self.notification_config.get('enabled', False),
            'smtp_server': self.notification_config.get('smtp_server', 'Not configured'),
            'smtp_port': self.notification_config.get('smtp_port', 25),
            'from_email': self.notification_config.get('from_email', 'Not configured'),
            'recipients': len(self.notification_config.get('to_emails', [])),
            'notify_on_success': self.notification_config.get('notify_on_success', False),
            'notify_on_failure': self.notification_config.get('notify_on_failure', True)
        }
