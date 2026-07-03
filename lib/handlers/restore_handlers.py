"""
Restore Menu Handlers
Handles all restore-related menu operations
"""

from ..utils import logger


class RestoreHandlers:
    """Handles restore menu operations

    Every per-service handler shares one list -> select -> confirm ->
    run -> report flow (_run_restore); the per-service dialog texts
    live in RESTORE_OPERATIONS. Confirm texts use a {backup}
    placeholder for the selected archive name.
    """

    RESTORE_OPERATIONS = {
        'nginx': {
            'title': 'Restore nginx',
            'name': 'nginx',
            'method': 'restore_nginx',
            'menu_hint': 'Backup Management → Backup nginx',
            'confirm': (
                "This will restore nginx from remote Borg archive:\n\n"
                "  {backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "WARNING:\n"
                "  • Current nginx installation will be backed up locally\n"
                "  • Services will be stopped during restore\n"
                "  • This may take 5-10 minutes\n\n"
                "Continue?"
            ),
            'infobox': (
                "Downloading and restoring nginx from remote Borg archive...\n\n"
                "This may take 5-10 minutes.\n"
                "Please be patient..."
            ),
            'success': (
                "nginx restored successfully!\n\n"
                "Service has been started and verified.\n"
                "A pre-restore backup was created for safety."
            ),
        },
        'mailcow': {
            'title': 'Restore Mailcow',
            'name': 'Mailcow',
            'method': 'restore_mailcow',
            'menu_hint': 'Backup Management → Backup Mailcow',
            'confirm': (
                "This will restore Mailcow from remote Borg archive:\n\n"
                "  {backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "WARNING:\n"
                "  • Current Mailcow installation will be backed up locally\n"
                "  • Email services will be unavailable during restore\n"
                "  • This may take 30-60 minutes\n"
                "  • You may need to verify DNS records after restore\n\n"
                "Continue?"
            ),
            'infobox': (
                "Downloading and restoring Mailcow from remote Borg archive...\n\n"
                "This may take 30-60 minutes.\n"
                "Please be very patient..."
            ),
            'success': (
                "Mailcow restored successfully!\n\n"
                "Services have been started and verified.\n\n"
                "IMPORTANT:\n"
                "  • Verify DNS records match your domain\n"
                "  • Send a test email to verify functionality\n"
                "  • DKIM keys have been restored"
            ),
        },
        'mailcow-directory': {
            'title': 'Restore Mailcow Directory',
            'name': 'Mailcow directory',
            'method': 'restore_mailcow_directory',
            'menu_hint': 'Backup Management → Backup Mailcow Directory',
            'confirm': (
                "This will restore Mailcow directory from remote Borg archive:\n\n"
                "  {backup}\n\n"
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
                "Continue?"
            ),
            'infobox': (
                "Downloading and restoring Mailcow directory from remote Borg archive...\n\n"
                "This may take 5-10 minutes.\n"
                "Please be patient..."
            ),
            'success': (
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
            ),
        },
        'monitoring-stack': {
            'title': 'Restore Monitoring Stack',
            'name': 'Monitoring stack',
            'method': 'restore_monitoring_stack',
            'menu_hint': 'Backup Management → Backup Monitoring Stack',
            'confirm': (
                "This will restore the monitoring stack from remote Borg archive:\n\n"
                "  {backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "This restores:\n"
                "  • Grafana dashboards, config, and plugins\n"
                "  • InfluxDB time-series data and config\n"
                "  • pressuresuite-influx-bridge code and credentials\n\n"
                "WARNING:\n"
                "  • Grafana and InfluxDB will be stopped during restore\n"
                "  • Existing data will be backed up locally (pre-restore)\n"
                "  • This may take 5-10 minutes\n\n"
                "Continue?"
            ),
            'infobox': (
                "Downloading and restoring monitoring stack from remote Borg archive...\n\n"
                "This may take 5-10 minutes.\n"
                "Please be patient..."
            ),
            'success': (
                "Monitoring stack restored successfully!\n\n"
                "Services have been started and verified.\n\n"
                "VERIFY:\n"
                "  • Grafana dashboards are accessible\n"
                "  • InfluxDB data is intact\n"
                "  • pressuresuite bridge timer is running"
            ),
        },
        'credentials': {
            'title': 'Restore Credentials',
            'name': 'Credentials',
            'method': 'restore_credentials',
            'menu_hint': 'Backup Management → Backup Credentials',
            'confirm': (
                "This will restore credentials from remote Borg archive:\n\n"
                "  {backup}\n\n"
                "Source: Remote rsync server (Borg repository)\n\n"
                "This restores:\n"
                "  • /root/.credentials.env (API tokens)\n"
                "  • /root/.dns-config (domain-to-provider mapping)\n\n"
                "Certbot credential files will also be synced.\n\n"
                "Continue?"
            ),
            'infobox': (
                "Downloading and restoring credentials from remote Borg archive...\n\n"
                "This should be very fast."
            ),
            'success': (
                "Credentials restored successfully!\n\n"
                "Certbot credential files have been synced."
            ),
        },
    }

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

    def _run_restore(self, key):
        """Shared list -> select -> confirm -> run -> report restore flow"""
        spec = self.RESTORE_OPERATIONS[key]

        try:
            restore_mgr = self._get_restore_manager()

            # List available backups
            self.ui.show_infobox("Retrieving backup list from remote Borg archive...\n\nPlease wait...")
            backups = restore_mgr.list_remote_backups(key)

            if not backups:
                self.ui.show_error(
                    f"No {spec['name']} backups found on remote server.\n\n"
                    "Create a backup first:\n"
                    f"  {spec['menu_hint']}"
                )
                return

            # Build selection list: 'latest' plus the 10 most recent, newest first
            backup_items = [("latest", "Latest backup (recommended)")]
            for backup in reversed(backups[-10:]):
                backup_items.append((backup['name'], backup['name']))

            # Show selection dialog
            selected_backup = self.ui.select_from_list(
                backup_items,
                f"Select {spec['name']} backup to restore (remote Borg archive):",
                spec['title']
            )

            if not selected_backup:
                return

            # Confirm restore
            if not self.ui.confirm_action(
                spec['confirm'].format(backup=selected_backup),
                spec['title']
            ):
                return

            self.ui.show_infobox(spec['infobox'])

            success = getattr(restore_mgr, spec['method'])(selected_backup)

            if success:
                self.ui.show_success(spec['success'])
                logger.info(f"{spec['name']} restore completed via TUI from {selected_backup}")
            else:
                self.ui.show_error(f"{spec['name']} restore failed. Check logs for details.")

        except Exception as e:
            logger.error(f"{spec['name']} restore error: {e}")
            self.ui.show_error(f"Restore failed:\n\n{e}")

    def handle_restore_nginx(self):
        """Restore nginx from backup"""
        self._run_restore('nginx')

    def handle_restore_mailcow(self):
        """Restore Mailcow from backup"""
        self._run_restore('mailcow')

    def handle_restore_mailcow_directory(self):
        """Restore Mailcow directory (configuration and certificates) from backup"""
        self._run_restore('mailcow-directory')

    def handle_restore_monitoring_stack(self):
        """Restore monitoring stack from backup"""
        self._run_restore('monitoring-stack')

    def handle_restore_credentials(self):
        """Restore credentials from backup"""
        self._run_restore('credentials')

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
