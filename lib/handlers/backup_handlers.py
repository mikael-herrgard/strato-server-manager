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
        # Show backup type selection
        backup_types = [
            ("all", "Complete backup (recommended)", True),
            ("config", "Configuration only", False),
            ("mail", "Mail data only", False),
            ("db", "Database only", False)
        ]

        code, backup_type = self.ui.show_radiolist(
            backup_types,
            "Select Mailcow backup type:\n\n"
            "Complete backup includes all data and is recommended.",
            "Mailcow Backup Type"
        )

        if code != self.ui.d.OK:
            return

        if not self.ui.confirm_action(
            f"This will create a {backup_type} backup of Mailcow.\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 15-60 minutes depending on your mail volume.\n\n"
            "Continue?",
            "Backup Mailcow"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox(
                f"Creating Mailcow backup ({backup_type})...\n\n"
                "This may take 15-60 minutes.\n"
                "Please be patient..."
            )

            success = backup_mgr.backup_mailcow(backup_type=backup_type, verify=True)

            if success:
                self.ui.show_success(
                    f"Mailcow backup ({backup_type}) completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info(f"Mailcow backup ({backup_type}) completed via TUI")
            else:
                self.ui.show_error("Mailcow backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_view_backup_status(self):
        """View backup status"""
        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Retrieving backup status...\n\nPlease wait...")

            status = backup_mgr.get_backup_status()

            # Build status text
            status_text = "Backup Status\n"
            status_text += "=" * 60 + "\n\n"

            for service, info in status.items():
                status_text += f"{service.upper()}:\n"
                status_text += f"  Repository: {info['repository']}\n"
                status_text += f"  Backup Count: {info['backup_count']}\n"
                if info['latest_backup']:
                    status_text += f"  Latest Backup: {info['latest_backup']}\n"
                else:
                    status_text += "  Latest Backup: None\n"
                status_text += "\n"

            self.ui.show_scrollable_text(status_text, "Backup Status")

        except Exception as e:
            logger.error(f"Failed to get backup status: {e}")
            self.ui.show_error(f"Failed to get backup status:\n\n{e}")
