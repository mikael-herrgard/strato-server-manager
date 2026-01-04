"""
Scheduling Menu Handlers
Handles all scheduling and automation menu operations
"""

from ..utils import logger


class SchedulingHandlers:
    """Handles scheduling and automation menu operations"""

    def __init__(self, ui, scheduling_manager, notification_manager):
        """
        Initialize scheduling handlers

        Args:
            ui: ServerManagerUI instance
            scheduling_manager: SchedulingManager instance (or callable)
            notification_manager: NotificationManager instance (or callable)
        """
        self.ui = ui
        self._scheduling_manager = scheduling_manager
        self._notification_manager = notification_manager

    def _get_scheduling_manager(self):
        """Get scheduling manager (lazy initialization support)"""
        if callable(self._scheduling_manager):
            return self._scheduling_manager()
        return self._scheduling_manager

    def _get_notification_manager(self):
        """Get notification manager (lazy initialization support)"""
        if callable(self._notification_manager):
            return self._notification_manager()
        return self._notification_manager

    def handle_view_schedules(self):
        """View current schedules"""
        try:
            sched_mgr = self._get_scheduling_manager()

            schedule = sched_mgr.get_current_schedule()

            if not schedule['exists'] or not schedule['jobs']:
                self.ui.show_info(
                    "No scheduled tasks found.\n\n"
                    "Use the scheduling menu to set up automated tasks:\n"
                    "  • Automated backups\n"
                    "  • Automated cleanup\n"
                    "  • Scheduled maintenance",
                    "No Schedules"
                )
                return

            # Build schedule display
            text = "Current Scheduled Tasks\n"
            text += "=" * 95 + "\n\n"

            for job in schedule['jobs']:
                text += f"Job Type: {job['type']}\n"
                text += f"  Schedule: {job['schedule']}\n"
                text += f"  Description: {sched_mgr.get_schedule_description(job['schedule'])}\n"

                next_run = sched_mgr.get_next_run_time(job['schedule'])
                if next_run:
                    text += f"  Next Run: {next_run}\n"

                # Display full command path without truncation for better visibility
                text += f"  Command: {job['command']}\n"
                text += "\n"

            self.ui.show_scrollable_text(text, "Current Schedules")

        except Exception as e:
            logger.error(f"View schedules error: {e}")
            self.ui.show_error(f"Failed to view schedules:\n\n{e}")

    def handle_schedule_backup(self):
        """Schedule automated backup"""
        try:
            sched_mgr = self._get_scheduling_manager()

            # Select service
            services = [
                ("nginx", "nginx Proxy Manager"),
                ("mailcow", "Mailcow Data Backup"),
                ("mailcow-directory", "Mailcow Directory (Config & Certificates)"),
                ("application", "Server Manager Application")
            ]

            code, service = self.ui.d.menu(
                "Select service to schedule backup:",
                title="Schedule Backup",
                choices=services,
                width=80,
                height=16
            )

            if code != self.ui.d.OK:
                return

            # Select schedule preset
            presets = sched_mgr.get_schedule_presets()
            preset_choices = [
                ("daily_2am", "Daily at 2:00 AM (recommended)"),
                ("daily_3am", "Daily at 3:00 AM"),
                ("daily_4am", "Daily at 4:00 AM"),
                ("daily_midnight", "Daily at midnight"),
                ("weekly_sunday_2am", "Weekly on Sunday at 2:00 AM"),
                ("every_12_hours", "Every 12 hours"),
                ("custom", "Custom schedule (advanced)")
            ]

            code, preset = self.ui.d.menu(
                f"Select schedule for {service} backup:\n\n"
                "Recommended: Daily at 2:00 AM (off-peak hours)",
                title="Backup Schedule",
                choices=preset_choices,
                width=60,
                height=18
            )

            if code != self.ui.d.OK:
                return

            if preset == "custom":
                code, custom_schedule = self.ui.d.inputbox(
                    "Enter custom cron schedule:\n\n"
                    "Format: minute hour day month weekday\n"
                    "Example: 0 2 * * * (daily at 2:00 AM)\n\n"
                    "Cron format guide:\n"
                    "  * * * * * = every minute\n"
                    "  0 2 * * * = daily at 2:00 AM\n"
                    "  0 */6 * * * = every 6 hours\n"
                    "  0 2 * * 0 = weekly on Sunday at 2:00 AM",
                    title="Custom Schedule",
                    width=70,
                    height=18
                )

                if code != self.ui.d.OK:
                    return

                schedule_expr = custom_schedule.strip()
            else:
                schedule_expr = presets[preset]

            # Select options
            code = self.ui.d.yesno(
                f"Schedule {service} backup:\n\n"
                f"Schedule: {sched_mgr.get_schedule_description(schedule_expr)}\n"
                f"Expression: {schedule_expr}\n\n"
                "Options:\n"
                "  • Verify backup integrity: Yes\n"
                "  • Notifications: As configured\n\n"
                "This will replace any existing schedule for this service.\n\n"
                "Continue?",
                title="Confirm Schedule",
                width=60,
                height=18
            )

            if code != self.ui.d.OK:
                return

            self.ui.show_infobox("Scheduling backup...\n\nPlease wait...")

            success = sched_mgr.schedule_backup(
                service,
                schedule_expr,
                options={'verify': True, 'remote': True}
            )

            if success:
                self.ui.show_success(
                    f"{service.capitalize()} backup scheduled successfully!\n\n"
                    f"Schedule: {sched_mgr.get_schedule_description(schedule_expr)}\n"
                    f"Expression: {schedule_expr}\n\n"
                    "Backups will run automatically at the scheduled time.\n"
                    "Logs: /opt/server-manager/logs/backup-{service}-cron.log"
                )
                logger.info(f"Scheduled {service} backup: {schedule_expr}")
            else:
                self.ui.show_error("Failed to schedule backup. Check logs for details.")

        except Exception as e:
            logger.error(f"Schedule backup error: {e}")
            self.ui.show_error(f"Failed to schedule backup:\n\n{e}")

    def handle_remove_schedule(self):
        """Remove scheduled task"""
        try:
            sched_mgr = self._get_scheduling_manager()

            schedule = sched_mgr.get_current_schedule()

            if not schedule['exists'] or not schedule['jobs']:
                self.ui.show_info("No scheduled tasks to remove.", "No Schedules")
                return

            # Build job list for selection
            job_choices = []
            for i, job in enumerate(schedule['jobs']):
                job_choices.append((
                    job['type'],
                    f"{job['type']} - {sched_mgr.get_schedule_description(job['schedule'])}"
                ))

            code, job_type = self.ui.d.menu(
                "Select task to remove:",
                title="Remove Schedule",
                choices=job_choices,
                width=70,
                height=20
            )

            if code != self.ui.d.OK:
                return

            if not self.ui.confirm_action(
                f"Remove scheduled task: {job_type}?\n\n"
                "This will stop the task from running automatically.\n"
                "You can reschedule it later if needed.",
                "Remove Schedule"
            ):
                return

            success = sched_mgr.remove_schedule(job_type)

            if success:
                self.ui.show_success(f"Schedule removed: {job_type}")
                logger.info(f"Removed schedule: {job_type}")
            else:
                self.ui.show_error("Failed to remove schedule. Check logs for details.")

        except Exception as e:
            logger.error(f"Remove schedule error: {e}")
            self.ui.show_error(f"Failed to remove schedule:\n\n{e}")

    def handle_schedule_cleanup(self):
        """Schedule automated cleanup"""
        try:
            sched_mgr = self._get_scheduling_manager()

            # Select retention period
            retention_choices = [
                ("30", "30 days (recommended)"),
                ("60", "60 days"),
                ("90", "90 days"),
                ("180", "180 days (6 months)"),
                ("custom", "Custom retention period")
            ]

            code, retention = self.ui.d.menu(
                "Select backup retention period:\n\n"
                "Backups older than this will be removed automatically.",
                title="Retention Period",
                choices=retention_choices,
                width=60,
                height=16
            )

            if code != self.ui.d.OK:
                return

            if retention == "custom":
                code, custom_days = self.ui.d.inputbox(
                    "Enter retention period in days:",
                    title="Custom Retention",
                    width=50,
                    height=10
                )

                if code != self.ui.d.OK:
                    return

                try:
                    retention_days = int(custom_days)
                    if retention_days < 1:
                        raise ValueError("Retention must be at least 1 day")
                except ValueError as e:
                    self.ui.show_error(f"Invalid retention period: {e}")
                    return
            else:
                retention_days = int(retention)

            # Select schedule
            schedule_choices = [
                ("weekly_sunday_2am", "Weekly on Sunday at 2:00 AM (recommended)"),
                ("daily_3am", "Daily at 3:00 AM"),
                ("weekly_monday_2am", "Weekly on Monday at 2:00 AM")
            ]

            code, schedule_key = self.ui.d.menu(
                f"Select cleanup schedule:\n\n"
                f"Retention: {retention_days} days",
                title="Cleanup Schedule",
                choices=schedule_choices,
                width=60,
                height=14
            )

            if code != self.ui.d.OK:
                return

            presets = sched_mgr.get_schedule_presets()
            schedule_expr = presets[schedule_key]

            if not self.ui.confirm_action(
                f"Schedule automated backup cleanup:\n\n"
                f"Retention: {retention_days} days\n"
                f"Schedule: {sched_mgr.get_schedule_description(schedule_expr)}\n\n"
                "Backups older than the retention period will be removed automatically.\n\n"
                "Continue?",
                "Confirm Cleanup Schedule"
            ):
                return

            self.ui.show_infobox("Scheduling cleanup...\n\nPlease wait...")

            success = sched_mgr.schedule_cleanup(schedule_expr, retention_days)

            if success:
                self.ui.show_success(
                    f"Cleanup scheduled successfully!\n\n"
                    f"Retention: {retention_days} days\n"
                    f"Schedule: {sched_mgr.get_schedule_description(schedule_expr)}\n\n"
                    "Old backups will be removed automatically."
                )
                logger.info(f"Scheduled cleanup: {schedule_expr} (retention: {retention_days} days)")
            else:
                self.ui.show_error("Failed to schedule cleanup. Check logs for details.")

        except Exception as e:
            logger.error(f"Schedule cleanup error: {e}")
            self.ui.show_error(f"Failed to schedule cleanup:\n\n{e}")

    def handle_configure_notifications(self):
        """Configure email notifications"""
        try:
            notif_mgr = self._get_notification_manager()

            # Get current config
            current_config = notif_mgr.notification_config

            # Enable/disable
            code = self.ui.d.yesno(
                "Enable email notifications?\n\n"
                "Email notifications can alert you when:\n"
                "  • Scheduled backups complete\n"
                "  • Backups fail\n"
                "  • Maintenance tasks complete\n"
                "  • Health checks detect issues\n\n"
                f"Current status: {'Enabled' if current_config.get('enabled') else 'Disabled'}",
                title="Enable Notifications",
                width=60,
                height=16
            )

            enabled = (code == self.ui.d.OK)

            if not enabled:
                current_config['enabled'] = False
                notif_mgr.save_notification_config(current_config)
                self.ui.show_info("Email notifications disabled.", "Notifications")
                return

            # SMTP Server
            code, smtp_server = self.ui.d.inputbox(
                "Enter SMTP server address:\n\n"
                "Examples:\n"
                "  • localhost (if local mail server)\n"
                "  • smtp.gmail.com (for Gmail)\n"
                "  • smtp.office365.com (for Office 365)\n"
                "  • mail.yourdomain.com",
                title="SMTP Server",
                init=current_config.get('smtp_server', 'localhost'),
                width=60,
                height=16
            )

            if code != self.ui.d.OK:
                return

            # SMTP Port
            code, smtp_port = self.ui.d.inputbox(
                "Enter SMTP port:\n\n"
                "Common ports:\n"
                "  • 25 (standard SMTP)\n"
                "  • 587 (SMTP with STARTTLS)\n"
                "  • 465 (SMTP with SSL)",
                title="SMTP Port",
                init=str(current_config.get('smtp_port', 25)),
                width=50,
                height=14
            )

            if code != self.ui.d.OK:
                return

            try:
                smtp_port = int(smtp_port)
            except ValueError:
                self.ui.show_error("Invalid port number")
                return

            # Use TLS?
            code = self.ui.d.yesno(
                "Use TLS/STARTTLS?\n\n"
                "Select Yes if using port 587 or if your SMTP server requires TLS.\n"
                "Select No for port 25 or local mail servers.",
                title="Use TLS",
                width=60,
                height=12
            )

            use_tls = (code == self.ui.d.OK)

            # SMTP Authentication
            code = self.ui.d.yesno(
                "Does your SMTP server require authentication?\n\n"
                "Most external SMTP servers (Gmail, Office365, etc.) require authentication.\n"
                "Local mail servers often don't.",
                title="SMTP Authentication",
                width=60,
                height=13
            )

            smtp_user = ""
            smtp_password = ""

            if code == self.ui.d.OK:
                code, smtp_user = self.ui.d.inputbox(
                    "Enter SMTP username:",
                    title="SMTP Username",
                    init=current_config.get('smtp_user', ''),
                    width=50,
                    height=10
                )

                if code != self.ui.d.OK:
                    return

                code, smtp_password = self.ui.d.passwordbox(
                    "Enter SMTP password:",
                    title="SMTP Password",
                    width=50,
                    height=10
                )

                if code != self.ui.d.OK:
                    return

            # From email
            code, from_email = self.ui.d.inputbox(
                "Enter 'From' email address:\n\n"
                "This is the sender address that will appear in notifications.",
                title="From Email",
                init=current_config.get('from_email', 'server-manager@localhost'),
                width=60,
                height=12
            )

            if code != self.ui.d.OK:
                return

            # To emails
            code, to_emails_str = self.ui.d.inputbox(
                "Enter recipient email addresses:\n\n"
                "Separate multiple addresses with commas.\n"
                "Example: admin@example.com, alerts@example.com",
                title="Recipient Emails",
                init=','.join(current_config.get('to_emails', [])),
                width=60,
                height=14
            )

            if code != self.ui.d.OK:
                return

            to_emails = [email.strip() for email in to_emails_str.split(',') if email.strip()]

            if not to_emails:
                self.ui.show_error("At least one recipient email is required")
                return

            # Notification preferences
            code = self.ui.d.yesno(
                "Send notifications for successful operations?\n\n"
                "Yes: Get notified for all operations (success and failure)\n"
                "No: Only get notified for failures (recommended)",
                title="Notification Preferences",
                width=60,
                height=13
            )

            notify_on_success = (code == self.ui.d.OK)

            # Save configuration
            new_config = {
                'enabled': True,
                'smtp_server': smtp_server,
                'smtp_port': smtp_port,
                'smtp_use_tls': use_tls,
                'smtp_user': smtp_user,
                'smtp_password': smtp_password,
                'from_email': from_email,
                'to_emails': to_emails,
                'notify_on_success': notify_on_success,
                'notify_on_failure': True
            }

            if notif_mgr.save_notification_config(new_config):
                self.ui.show_success(
                    "Email notifications configured successfully!\n\n"
                    f"SMTP Server: {smtp_server}:{smtp_port}\n"
                    f"From: {from_email}\n"
                    f"Recipients: {', '.join(to_emails)}\n\n"
                    "Would you like to send a test email?"
                )

                # Offer to send test
                code = self.ui.d.yesno(
                    "Send test notification?",
                    title="Test Notification",
                    width=50,
                    height=8
                )

                if code == self.ui.d.OK:
                    self.handle_test_notification()

                logger.info("Email notifications configured")
            else:
                self.ui.show_error("Failed to save notification configuration")

        except Exception as e:
            logger.error(f"Configure notifications error: {e}")
            self.ui.show_error(f"Failed to configure notifications:\n\n{e}")

    def handle_test_notification(self):
        """Send test notification"""
        try:
            notif_mgr = self._get_notification_manager()

            if not notif_mgr.is_configured():
                self.ui.show_error(
                    "Email notifications not configured.\n\n"
                    "Please configure notifications first.",
                    "Not Configured"
                )
                return

            self.ui.show_infobox("Sending test notification...\n\nPlease wait...")

            result = notif_mgr.test_notification()

            if result['success']:
                self.ui.show_success(
                    "Test notification sent successfully!\n\n"
                    "Check your email inbox.\n"
                    "If you don't receive it, check spam/junk folder."
                )
                logger.info("Test notification sent")
            else:
                self.ui.show_error(
                    f"Failed to send test notification.\n\n"
                    f"Error: {result.get('error', 'Unknown error')}\n\n"
                    "Check your SMTP settings and try again."
                )

        except Exception as e:
            logger.error(f"Test notification error: {e}")
            self.ui.show_error(f"Failed to send test notification:\n\n{e}")

    def handle_notification_status(self):
        """View notification status"""
        try:
            notif_mgr = self._get_notification_manager()

            status = notif_mgr.get_notification_status()

            text = "Email Notification Status\n"
            text += "=" * 95 + "\n\n"

            text += f"Configured: {'Yes' if status['configured'] else 'No'}\n"
            text += f"Enabled: {'Yes' if status['enabled'] else 'No'}\n\n"

            if status['configured']:
                text += "Configuration:\n"
                text += f"  SMTP Server: {status['smtp_server']}:{status['smtp_port']}\n"
                text += f"  From: {status['from_email']}\n"
                text += f"  Recipients: {status['recipients']} address(es)\n\n"

                text += "Preferences:\n"
                text += f"  Notify on success: {'Yes' if status['notify_on_success'] else 'No'}\n"
                text += f"  Notify on failure: {'Yes' if status['notify_on_failure'] else 'No'}\n"
            else:
                text += "Not configured. Use 'Configure Notifications' to set up email alerts."

            self.ui.show_scrollable_text(text, "Notification Status")

        except Exception as e:
            logger.error(f"Notification status error: {e}")
            self.ui.show_error(f"Failed to get notification status:\n\n{e}")
