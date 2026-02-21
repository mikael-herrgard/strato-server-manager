"""
Restore Menu Handlers
Handles all restore-related menu operations
"""

from ..utils import logger


class RestoreHandlers:
    """Handles restore menu operations"""

    def __init__(self, ui, restore_manager):
        """
        Initialize restore handlers

        Args:
            ui: ServerManagerUI instance
            restore_manager: RestoreManager instance (or callable to get it)
        """
        self.ui = ui
        self._restore_manager = restore_manager

    def _get_restore_manager(self):
        """Get restore manager (lazy initialization support)"""
        if callable(self._restore_manager):
            return self._restore_manager()
        return self._restore_manager

    def handle_restore_nginx(self):
        """Restore nginx from backup"""
        try:
            restore_mgr = self._get_restore_manager()

            # List available backups
            self.ui.show_infobox("Retrieving backup list from remote Borg archive...\n\nPlease wait...")
            backups = restore_mgr.list_remote_backups('nginx')

            if not backups:
                self.ui.show_error(
                    "No nginx backups found on remote server.\n\n"
                    "Create a backup first:\n"
                    "  Backup Management → Backup nginx"
                )
                return

            # Build selection list
            backup_items = [("latest", "Latest backup (recommended)")]
            for backup in backups[:10]:  # Show last 10
                backup_items.append((backup['name'], backup['name']))

            # Show selection dialog
            selected_backup = self.ui.select_from_list(
                backup_items,
                "Select nginx backup to restore (remote Borg archive):",
                "Restore nginx"
            )

            if not selected_backup:
                return

            # Confirm restore
            if not self.ui.confirm_action(
                f"This will restore nginx from remote Borg archive:\n\n"
                f"  {selected_backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "WARNING:\n"
                "  • Current nginx installation will be backed up locally\n"
                "  • Services will be stopped during restore\n"
                "  • This may take 5-10 minutes\n\n"
                "Continue?",
                "Restore nginx"
            ):
                return

            self.ui.show_infobox(
                "Downloading and restoring nginx from remote Borg archive...\n\n"
                "This may take 5-10 minutes.\n"
                "Please be patient..."
            )

            success = restore_mgr.restore_nginx(selected_backup)

            if success:
                self.ui.show_success(
                    "nginx restored successfully!\n\n"
                    "Service has been started and verified.\n"
                    "A pre-restore backup was created for safety."
                )
                logger.info(f"nginx restore completed via TUI from {selected_backup}")
            else:
                self.ui.show_error("nginx restore failed. Check logs for details.")

        except Exception as e:
            logger.error(f"nginx restore error: {e}")
            self.ui.show_error(f"Restore failed:\n\n{e}")

    def handle_restore_mailcow(self):
        """Restore Mailcow from backup"""
        try:
            restore_mgr = self._get_restore_manager()

            # List available backups
            self.ui.show_infobox("Retrieving backup list from remote Borg archive...\n\nPlease wait...")
            backups = restore_mgr.list_remote_backups('mailcow')

            if not backups:
                self.ui.show_error(
                    "No Mailcow backups found on remote server.\n\n"
                    "Create a backup first:\n"
                    "  Backup Management → Backup Mailcow"
                )
                return

            # Build selection list
            backup_items = [("latest", "Latest backup (recommended)")]
            for backup in backups[:10]:  # Show last 10
                backup_items.append((backup['name'], backup['name']))

            # Show selection dialog
            selected_backup = self.ui.select_from_list(
                backup_items,
                "Select Mailcow backup to restore (remote Borg archive):",
                "Restore Mailcow"
            )

            if not selected_backup:
                return

            # Confirm restore
            if not self.ui.confirm_action(
                f"This will restore Mailcow from remote Borg archive:\n\n"
                f"  {selected_backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "WARNING:\n"
                "  • Current Mailcow installation will be backed up locally\n"
                "  • Email services will be unavailable during restore\n"
                "  • This may take 30-60 minutes\n"
                "  • You may need to verify DNS records after restore\n\n"
                "Continue?",
                "Restore Mailcow"
            ):
                return

            self.ui.show_infobox(
                "Downloading and restoring Mailcow from remote Borg archive...\n\n"
                "This may take 30-60 minutes.\n"
                "Please be very patient..."
            )

            success = restore_mgr.restore_mailcow(selected_backup)

            if success:
                self.ui.show_success(
                    "Mailcow restored successfully!\n\n"
                    "Services have been started and verified.\n\n"
                    "IMPORTANT:\n"
                    "  • Verify DNS records match your domain\n"
                    "  • Send a test email to verify functionality\n"
                    "  • DKIM keys have been restored"
                )
                logger.info(f"Mailcow restore completed via TUI from {selected_backup}")
            else:
                self.ui.show_error("Mailcow restore failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow restore error: {e}")
            self.ui.show_error(f"Restore failed:\n\n{e}")

    def handle_restore_mailcow_directory(self):
        """Restore Mailcow directory (configuration and certificates) from backup"""
        try:
            restore_mgr = self._get_restore_manager()

            # List available backups
            self.ui.show_infobox("Retrieving backup list from remote Borg archive...\n\nPlease wait...")
            backups = restore_mgr.list_remote_backups('mailcow-directory')

            if not backups:
                self.ui.show_error(
                    "No Mailcow directory backups found on remote server.\n\n"
                    "Create a backup first:\n"
                    "  Backup Management → Backup Mailcow Directory"
                )
                return

            # Build selection list
            backup_items = [("latest", "Latest backup (recommended)")]
            for backup in backups[:10]:  # Show last 10
                backup_items.append((backup['name'], backup['name']))

            # Show selection dialog
            selected_backup = self.ui.select_from_list(
                backup_items,
                "Select Mailcow directory backup to restore (remote Borg archive):",
                "Restore Mailcow Directory"
            )

            if not selected_backup:
                return

            # Confirm restore
            if not self.ui.confirm_action(
                f"This will restore Mailcow directory from remote Borg archive:\n\n"
                f"  {selected_backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "This restores:\n"
                "  • Configuration files (mailcow.conf)\n"
                "  • SSL certificates\n"
                "  • DKIM keys\n"
                "  • Docker compose files\n\n"
                "WARNING:\n"
                "  • Mailcow services will be stopped\n"
                "  • Current directory will be backed up locally\n"
                "  • This may take 5-10 minutes\n"
                "  • You'll need to pull images and restore data separately\n\n"
                "Continue?",
                "Restore Mailcow Directory"
            ):
                return

            self.ui.show_infobox(
                "Downloading and restoring Mailcow directory from remote Borg archive...\n\n"
                "This may take 5-10 minutes.\n"
                "Please be patient..."
            )

            success = restore_mgr.restore_mailcow_directory(selected_backup)

            if success:
                self.ui.show_success(
                    "Mailcow directory restored successfully!\n\n"
                    "Configuration and certificates have been restored.\n\n"
                    "NEXT STEPS FOR FULL RECOVERY:\n"
                    "  1. Pull Docker images:\n"
                    "     cd /opt/mailcow-dockerized && docker compose pull\n\n"
                    "  2. Start services to create volumes:\n"
                    "     docker compose up -d\n\n"
                    "  3. Stop services for data restore:\n"
                    "     docker compose down\n\n"
                    "  4. Restore mailcow data:\n"
                    "     Use 'Restore Mailcow Data' from menu\n\n"
                    "  5. Start services:\n"
                    "     docker compose up -d\n\n"
                    "See logs for detailed recovery instructions."
                )
                logger.info(f"Mailcow directory restore completed via TUI from {selected_backup}")
            else:
                self.ui.show_error("Mailcow directory restore failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow directory restore error: {e}")
            self.ui.show_error(f"Restore failed:\n\n{e}")

    def handle_restore_monitoring_stack(self):
        """Restore monitoring stack from backup"""
        try:
            restore_mgr = self._get_restore_manager()

            # List available backups
            self.ui.show_infobox("Retrieving backup list from remote Borg archive...\n\nPlease wait...")
            backups = restore_mgr.list_remote_backups('monitoring-stack')

            if not backups:
                self.ui.show_error(
                    "No monitoring stack backups found on remote server.\n\n"
                    "Create a backup first:\n"
                    "  Backup Management → Backup Monitoring Stack"
                )
                return

            # Build selection list
            backup_items = [("latest", "Latest backup (recommended)")]
            for backup in backups[:10]:  # Show last 10
                backup_items.append((backup['name'], backup['name']))

            # Show selection dialog
            selected_backup = self.ui.select_from_list(
                backup_items,
                "Select monitoring stack backup to restore (remote Borg archive):",
                "Restore Monitoring Stack"
            )

            if not selected_backup:
                return

            # Confirm restore
            if not self.ui.confirm_action(
                f"This will restore the monitoring stack from remote Borg archive:\n\n"
                f"  {selected_backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "This restores:\n"
                "  • Grafana dashboards, config, and plugins\n"
                "  • InfluxDB time-series data and config\n"
                "  • pressuresuite-influx-bridge code and credentials\n\n"
                "WARNING:\n"
                "  • Grafana and InfluxDB will be stopped during restore\n"
                "  • Existing data will be backed up locally (pre-restore)\n"
                "  • This may take 5-10 minutes\n\n"
                "Continue?",
                "Restore Monitoring Stack"
            ):
                return

            self.ui.show_infobox(
                "Downloading and restoring monitoring stack from remote Borg archive...\n\n"
                "This may take 5-10 minutes.\n"
                "Please be patient..."
            )

            success = restore_mgr.restore_monitoring_stack(selected_backup)

            if success:
                self.ui.show_success(
                    "Monitoring stack restored successfully!\n\n"
                    "Services have been started and verified.\n\n"
                    "VERIFY:\n"
                    "  • Grafana dashboards are accessible\n"
                    "  • InfluxDB data is intact\n"
                    "  • pressuresuite bridge timer is running"
                )
                logger.info(f"Monitoring stack restore completed via TUI from {selected_backup}")
            else:
                self.ui.show_error("Monitoring stack restore failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Monitoring stack restore error: {e}")
            self.ui.show_error(f"Restore failed:\n\n{e}")

    def handle_restore_credentials(self):
        """Restore credentials from backup"""
        try:
            restore_mgr = self._get_restore_manager()

            # List available backups
            self.ui.show_infobox("Retrieving backup list from remote Borg archive...\n\nPlease wait...")
            backups = restore_mgr.list_remote_backups('credentials')

            if not backups:
                self.ui.show_error(
                    "No credentials backups found on remote server.\n\n"
                    "Create a backup first:\n"
                    "  Backup Management → Backup Credentials"
                )
                return

            # Build selection list
            backup_items = [("latest", "Latest backup (recommended)")]
            for backup in backups[:10]:
                backup_items.append((backup['name'], backup['name']))

            # Show selection dialog
            selected_backup = self.ui.select_from_list(
                backup_items,
                "Select credentials backup to restore (remote Borg archive):",
                "Restore Credentials"
            )

            if not selected_backup:
                return

            # Confirm restore
            if not self.ui.confirm_action(
                f"This will restore credentials from remote Borg archive:\n\n"
                f"  {selected_backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "This restores:\n"
                "  • /root/.credentials.env (API tokens)\n"
                "  • /root/.dns-config (domain-to-provider mapping)\n\n"
                "Certbot credential files will also be synced.\n\n"
                "Continue?",
                "Restore Credentials"
            ):
                return

            self.ui.show_infobox(
                "Downloading and restoring credentials from remote Borg archive...\n\n"
                "This should be very fast."
            )

            success = restore_mgr.restore_credentials(selected_backup)

            if success:
                self.ui.show_success(
                    "Credentials restored successfully!\n\n"
                    "Certbot credential files have been synced."
                )
                logger.info(f"Credentials restore completed via TUI from {selected_backup}")
            else:
                self.ui.show_error("Credentials restore failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Credentials restore error: {e}")
            self.ui.show_error(f"Restore failed:\n\n{e}")

    def handle_list_backups(self):
        """List available backups"""
        try:
            restore_mgr = self._get_restore_manager()

            self.ui.show_infobox("Retrieving backup lists from remote Borg archive...\n\nPlease wait...")

            # Build backup list text
            backup_text = "Available Remote Backups (rsync/Borg)\n"
            backup_text += "=" * 95 + "\n"
            backup_text += "Storage: Remote rsync server via Borg repositories\n\n"

            for service in ['nginx', 'mailcow', 'mailcow-directory', 'server-manager', 'monitoring-stack', 'credentials']:
                backups = restore_mgr.list_remote_backups(service)

                backup_text += f"{service.upper()}:\n"
                if backups:
                    backup_text += f"  Total: {len(backups)} backups\n"
                    backup_text += "  Recent backups:\n"
                    for backup in reversed(backups[-5:]):  # Show 5 most recent, newest first
                        backup_text += f"    • {backup['name']}\n"
                else:
                    backup_text += "  No backups found\n"
                backup_text += "\n"

            self.ui.show_scrollable_text(backup_text, "Available Remote Backups (rsync/Borg)")

        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            self.ui.show_error(f"Failed to list backups:\n\n{e}")
