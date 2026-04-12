"""
Backup Menu Handlers
Handles all backup-related menu operations
"""

from ..utils import logger


class BackupHandlers:
    """Handles backup menu operations"""

    def __init__(self, ui, backup_manager):
        """
        Initialize backup handlers

        Args:
            ui: ServerManagerUI instance
            backup_manager: BackupManager instance (or callable to get it)
        """
        self.ui = ui
        self._backup_manager = backup_manager

    def _get_backup_manager(self):
        """Get backup manager (lazy initialization support)"""
        if callable(self._backup_manager):
            return self._backup_manager()
        return self._backup_manager

    def handle_backup_nginx(self):
        """Backup nginx Proxy Manager"""
        if not self.ui.confirm_action(
            "This will create a backup of nginx Proxy Manager.\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 2-5 minutes.\n\n"
            "Continue?",
            "Backup nginx"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating nginx backup...\n\nThis may take a few minutes.")

            success = backup_mgr.backup_nginx(verify=True)

            if success:
                self.ui.show_success(
                    "nginx backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("nginx backup completed via TUI")
            else:
                self.ui.show_error("nginx backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"nginx backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_mailcow(self):
        """Backup Mailcow"""
        if not self.ui.confirm_action(
            "This will create a complete backup of Mailcow.\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 15-60 minutes depending on your mail volume.\n\n"
            "Continue?",
            "Backup Mailcow"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox(
                "Creating Mailcow backup...\n\n"
                "This may take 15-60 minutes.\n"
                "Please be patient..."
            )

            success = backup_mgr.backup_mailcow(backup_type="all", verify=True)

            if success:
                self.ui.show_success(
                    "Mailcow backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("Mailcow backup completed via TUI")
            else:
                self.ui.show_error("Mailcow backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_mailcow_directory(self):
        """Backup Mailcow directory (configuration and certificates)"""
        if not self.ui.confirm_action(
            "This will create a backup of the Mailcow installation directory.\n\n"
            "This includes:\n"
            "  • Configuration files (mailcow.conf)\n"
            "  • SSL certificates\n"
            "  • DKIM keys\n"
            "  • Docker compose files\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 2-5 minutes.\n\n"
            "Continue?",
            "Backup Mailcow Directory"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating Mailcow directory backup...\n\nThis may take a few minutes.")

            success = backup_mgr.backup_mailcow_directory(verify=True)

            if success:
                self.ui.show_success(
                    "Mailcow directory backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("Mailcow directory backup completed via TUI")
            else:
                self.ui.show_error("Mailcow directory backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow directory backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_server_manager(self):
        """Backup Server-Manager configuration"""
        if not self.ui.confirm_action(
            "This will create a backup of Server-Manager configuration.\n\n"
            "The backup includes:\n"
            "  • settings.yaml\n"
            "  • notifications.yaml\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "Continue?",
            "Backup Server-Manager"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating Server-Manager config backup...\n\nThis may take a few minutes.")

            success = backup_mgr.backup_server_manager(verify=True)

            if success:
                self.ui.show_success(
                    "Server-Manager config backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("Server-Manager config backup completed via TUI")
            else:
                self.ui.show_error("Server-Manager config backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Server-Manager config backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_monitoring_stack(self):
        """Backup Monitoring Stack (Grafana/InfluxDB/pressuresuite bridge)"""
        if not self.ui.confirm_action(
            "This will create a backup of the Monitoring Stack.\n\n"
            "The backup includes:\n"
            "  • Grafana dashboards, config, and plugins\n"
            "  • InfluxDB time-series data and config\n"
            "  • pressuresuite-influx-bridge code and credentials\n"
            "  • Associated systemd service/timer units\n\n"
            "NOTE: Grafana and InfluxDB will be briefly stopped\n"
            "during the backup for data consistency.\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "Continue?",
            "Backup Monitoring Stack"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox(
                "Creating monitoring stack backup...\n\n"
                "Stopping Grafana and InfluxDB for consistent snapshot.\n"
                "This may take a few minutes."
            )

            success = backup_mgr.backup_monitoring_stack(verify=True)

            if success:
                self.ui.show_success(
                    "Monitoring stack backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified.\n"
                    "Grafana and InfluxDB have been restarted."
                )
                logger.info("Monitoring stack backup completed via TUI")
            else:
                self.ui.show_error("Monitoring stack backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Monitoring stack backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_credentials(self):
        """Backup centralized credentials"""
        if not self.ui.confirm_action(
            "This will create a backup of centralized credentials.\n\n"
            "The backup includes:\n"
            "  • /root/.credentials.env (API tokens)\n"
            "  • /root/.dns-config (domain-to-provider mapping)\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "Continue?",
            "Backup Credentials"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating credentials backup...\n\nThis should be very fast.")

            success = backup_mgr.backup_credentials(verify=True)

            if success:
                self.ui.show_success(
                    "Credentials backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("Credentials backup completed via TUI")
            else:
                self.ui.show_error("Credentials backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Credentials backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_all(self):
        """Backup all services in sequence"""
        if not self.ui.confirm_action(
            "This will backup ALL services in sequence:\n\n"
            "  1. Credentials\n"
            "  2. nginx Proxy Manager\n"
            "  3. Mailcow Directory\n"
            "  4. Mailcow Data (complete)\n"
            "  5. Monitoring Stack\n"
            "  6. Server-Manager Config\n\n"
            "This may take 30-90 minutes depending on data volume.\n\n"
            "Continue?",
            "Backup All Services"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            results = {}

            # 1. Credentials
            self.ui.show_infobox("Backing up Credentials...\n\n(Step 1 of 6)")
            results['credentials'] = backup_mgr.backup_credentials(verify=True)

            # 2. nginx
            self.ui.show_infobox("Backing up nginx Proxy Manager...\n\n(Step 2 of 6)")
            results['nginx'] = backup_mgr.backup_nginx(verify=True)

            # 3. Mailcow Directory
            self.ui.show_infobox("Backing up Mailcow Directory...\n\n(Step 3 of 6)")
            results['mailcow-directory'] = backup_mgr.backup_mailcow_directory(verify=True)

            # 4. Mailcow Data
            self.ui.show_infobox("Backing up Mailcow Data...\n\n(Step 4 of 6)\nThis may take a while...")
            results['mailcow'] = backup_mgr.backup_mailcow(backup_type='all', verify=True)

            # 5. Monitoring Stack
            self.ui.show_infobox("Backing up Monitoring Stack...\n\n(Step 5 of 6)")
            results['monitoring-stack'] = backup_mgr.backup_monitoring_stack(verify=True)

            # 6. Server-Manager
            self.ui.show_infobox("Backing up Server-Manager Config...\n\n(Step 6 of 6)")
            results['server-manager'] = backup_mgr.backup_server_manager(verify=True)

            # Build summary
            succeeded = sum(1 for v in results.values() if v)
            total = len(results)

            summary = f"Backup All Services Complete: {succeeded}/{total} succeeded\n\n"
            for service, success in results.items():
                icon = "OK" if success else "FAILED"
                summary += f"  [{icon}] {service}\n"

            if succeeded == total:
                self.ui.show_success(summary)
                logger.info("Backup all services completed successfully via TUI")
            else:
                summary += "\nCheck logs for details on failed backups."
                self.ui.show_error(summary)
                logger.warning(f"Backup all services: {succeeded}/{total} succeeded")

        except Exception as e:
            logger.error(f"Backup all services error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_view_backup_status(self):
        """View backup status"""
        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Retrieving backup status from remote Borg archive...\n\nPlease wait...")

            status = backup_mgr.get_backup_status()

            # Build status text
            status_text = "Backup Status (Remote rsync/Borg)\n"
            status_text += "=" * 95 + "\n"
            status_text += "Storage: Remote rsync server via Borg repositories\n\n"

            for service, info in status.items():
                status_text += f"{service.upper()}:\n"
                status_text += f"  Repository: {info['repository']}\n"
                status_text += f"  Backup Count: {info['backup_count']}\n"
                if info['latest_backup']:
                    status_text += f"  Latest Backup: {info['latest_backup']}\n"
                else:
                    status_text += "  Latest Backup: None\n"
                status_text += "\n"

            self.ui.show_scrollable_text(status_text, "Backup Status (Remote rsync/Borg)")

        except Exception as e:
            logger.error(f"Failed to get backup status: {e}")
            self.ui.show_error(f"Failed to get backup status:\n\n{e}")

    def handle_initialize_repos(self):
        """Initialize all Borg backup repositories on remote server"""
        if not self.ui.confirm_action(
            "This will check and initialize all Borg backup repositories\n"
            "on the remote rsync server.\n\n"
            "Repositories:\n"
            "  • nginx-backup\n"
            "  • mailcow-backup\n"
            "  • mailcow-directory-backup\n"
            "  • server-manager-backup\n"
            "  • monitoring-stack-backup\n"
            "  • credentials-backup\n\n"
            "Existing repositories will be left untouched.\n"
            "Missing repositories will be created.\n\n"
            "This is useful when setting up a new backup provider.\n\n"
            "Continue?",
            "Initialize Backup Repositories"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox(
                "Checking and initializing Borg repositories...\n\n"
                "This may take a minute."
            )

            results = backup_mgr.initialize_all_repos()

            # Build summary
            succeeded = sum(1 for v in results.values() if v)
            total = len(results)

            summary = f"Repository Initialization: {succeeded}/{total} ready\n\n"
            for service, success in results.items():
                icon = "OK" if success else "FAILED"
                summary += f"  [{icon}] {service}-backup\n"

            if succeeded == total:
                self.ui.show_success(summary)
                logger.info("All Borg repositories initialized successfully via TUI")
            else:
                summary += "\nCheck logs for details on failed repositories."
                self.ui.show_error(summary)
                logger.warning(f"Repository initialization: {succeeded}/{total} succeeded")

        except Exception as e:
            logger.error(f"Repository initialization error: {e}")
            self.ui.show_error(f"Initialization failed:\n\n{e}")
