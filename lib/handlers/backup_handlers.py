"""
Backup Menu Handlers
Handles all backup-related menu operations
"""

from ..utils import logger


class BackupHandlers:
    """Handles backup menu operations

    Every per-service handler shares one confirm -> run -> report flow
    (_run_backup); the per-service dialog texts live in BACKUP_OPERATIONS.
    """

    BACKUP_OPERATIONS = {
        'nginx': {
            'title': 'Backup nginx',
            'name': 'nginx',
            'method': 'backup_nginx',
            'confirm': (
                "This will create a backup of nginx Proxy Manager.\n\n"
                "The backup will be stored on your rsync server.\n\n"
                "This may take 2-5 minutes.\n\n"
                "Continue?"
            ),
            'infobox': "Creating nginx backup...\n\nThis may take a few minutes.",
            'success': (
                "nginx backup completed successfully!\n\n"
                "The backup has been stored on your rsync server and verified."
            ),
        },
        'mailcow': {
            'title': 'Backup Mailcow',
            'name': 'Mailcow',
            'method': 'backup_mailcow',
            'kwargs': {'backup_type': 'all'},
            'confirm': (
                "This will create a complete backup of Mailcow.\n\n"
                "The backup will be stored on your rsync server.\n\n"
                "This may take 15-60 minutes depending on your mail volume.\n\n"
                "Continue?"
            ),
            'infobox': (
                "Creating Mailcow backup...\n\n"
                "This may take 15-60 minutes.\n"
                "Please be patient..."
            ),
            'success': (
                "Mailcow backup completed successfully!\n\n"
                "The backup has been stored on your rsync server and verified."
            ),
        },
        'mailcow-directory': {
            'title': 'Backup Mailcow Directory',
            'name': 'Mailcow directory',
            'method': 'backup_mailcow_directory',
            'confirm': (
                "This will create a backup of the Mailcow installation directory.\n\n"
                "This includes:\n"
                "  • Configuration files (mailcow.conf)\n"
                "  • SSL certificates\n"
                "  • DKIM keys\n"
                "  • Docker compose files\n\n"
                "The backup will be stored on your rsync server.\n\n"
                "This may take 2-5 minutes.\n\n"
                "Continue?"
            ),
            'infobox': "Creating Mailcow directory backup...\n\nThis may take a few minutes.",
            'success': (
                "Mailcow directory backup completed successfully!\n\n"
                "The backup has been stored on your rsync server and verified."
            ),
        },
        'monitoring-stack': {
            'title': 'Backup Monitoring Stack',
            'name': 'Monitoring stack',
            'method': 'backup_monitoring_stack',
            'confirm': (
                "This will create a backup of the Monitoring Stack.\n\n"
                "The backup includes:\n"
                "  • Grafana dashboards, config, and plugins\n"
                "  • InfluxDB time-series data and config\n"
                "  • pressuresuite-influx-bridge code and credentials\n"
                "  • Associated systemd service/timer units\n\n"
                "NOTE: Grafana and InfluxDB will be briefly stopped\n"
                "during the backup for data consistency.\n\n"
                "The backup will be stored on your rsync server.\n\n"
                "Continue?"
            ),
            'infobox': (
                "Creating monitoring stack backup...\n\n"
                "Stopping Grafana and InfluxDB for consistent snapshot.\n"
                "This may take a few minutes."
            ),
            'success': (
                "Monitoring stack backup completed successfully!\n\n"
                "The backup has been stored on your rsync server and verified.\n"
                "Grafana and InfluxDB have been restarted."
            ),
        },
        'server-manager': {
            'title': 'Backup Server-Manager',
            'name': 'Server-Manager config',
            'method': 'backup_server_manager',
            'confirm': (
                "This will create a backup of Server-Manager configuration.\n\n"
                "The backup includes:\n"
                "  • settings.yaml\n"
                "  • notifications.yaml\n\n"
                "The backup will be stored on your rsync server.\n\n"
                "Continue?"
            ),
            'infobox': "Creating Server-Manager config backup...\n\nThis may take a few minutes.",
            'success': (
                "Server-Manager config backup completed successfully!\n\n"
                "The backup has been stored on your rsync server and verified."
            ),
        },
        'credentials': {
            'title': 'Backup Credentials',
            'name': 'Credentials',
            'method': 'backup_credentials',
            'confirm': (
                "This will create a backup of centralized credentials.\n\n"
                "The backup includes:\n"
                "  • /root/.credentials.env (API tokens)\n"
                "  • /root/.dns-config (domain-to-provider mapping)\n\n"
                "The backup will be stored on your rsync server.\n\n"
                "Continue?"
            ),
            'infobox': "Creating credentials backup...\n\nThis should be very fast.",
            'success': (
                "Credentials backup completed successfully!\n\n"
                "The backup has been stored on your rsync server and verified."
            ),
        },
    }

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

    def _run_backup(self, key):
        """Shared confirm -> run -> report flow for a single service backup"""
        spec = self.BACKUP_OPERATIONS[key]

        if not self.ui.confirm_action(spec['confirm'], spec['title']):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox(spec['infobox'])

            method = getattr(backup_mgr, spec['method'])
            success = method(verify=True, **spec.get('kwargs', {}))

            if success:
                self.ui.show_success(spec['success'])
                logger.info(f"{spec['name']} backup completed via TUI")
            else:
                self.ui.show_error(f"{spec['name']} backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"{spec['name']} backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_nginx(self):
        """Backup nginx Proxy Manager"""
        self._run_backup('nginx')

    def handle_backup_mailcow(self):
        """Backup Mailcow"""
        self._run_backup('mailcow')

    def handle_backup_mailcow_directory(self):
        """Backup Mailcow directory (configuration and certificates)"""
        self._run_backup('mailcow-directory')

    def handle_backup_monitoring_stack(self):
        """Backup Monitoring Stack (Grafana/InfluxDB/pressuresuite bridge)"""
        self._run_backup('monitoring-stack')

    def handle_backup_server_manager(self):
        """Backup Server-Manager configuration"""
        self._run_backup('server-manager')

    def handle_backup_credentials(self):
        """Backup centralized credentials"""
        self._run_backup('credentials')

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

        # (service key, display label, method kwargs)
        sequence = [
            ('credentials', 'Credentials', {}),
            ('nginx', 'nginx Proxy Manager', {}),
            ('mailcow-directory', 'Mailcow Directory', {}),
            ('mailcow', 'Mailcow Data', {'backup_type': 'all'}),
            ('monitoring-stack', 'Monitoring Stack', {}),
            ('server-manager', 'Server-Manager Config', {}),
        ]

        try:
            backup_mgr = self._get_backup_manager()

            results = {}
            for step, (key, label, kwargs) in enumerate(sequence, 1):
                extra = "\nThis may take a while..." if key == 'mailcow' else ""
                self.ui.show_infobox(
                    f"Backing up {label}...\n\n(Step {step} of {len(sequence)}){extra}"
                )
                method = getattr(backup_mgr, self.BACKUP_OPERATIONS[key]['method'])
                results[key] = method(verify=True, **kwargs)

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
