"""
Maintenance Menu Handlers
Handles all maintenance-related menu operations
"""

from ..utils import logger, run_command


class MaintenanceHandlers:
    """Handles maintenance menu operations"""

    def __init__(self, ui, maintenance_manager, backup_manager=None):
        """
        Initialize maintenance handlers

        Args:
            ui: ServerManagerUI instance
            maintenance_manager: MaintenanceManager instance (or callable)
            backup_manager: BackupManager instance (or callable) - optional
        """
        self.ui = ui
        self._maintenance_manager = maintenance_manager
        self._backup_manager = backup_manager

    def _get_maintenance_manager(self):
        """Get maintenance manager (lazy initialization support)"""
        if callable(self._maintenance_manager):
            return self._maintenance_manager()
        return self._maintenance_manager

    def _get_backup_manager(self):
        """Get backup manager (lazy initialization support)"""
        if callable(self._backup_manager):
            return self._backup_manager()
        return self._backup_manager

    def handle_update_nginx(self):
        """Update nginx"""
        if not self.ui.confirm_action(
            "This will update nginx Proxy Manager to the latest version.\n\n"
            "A local directory backup will be created before the update.\n\n"
            "The update process:\n"
            "  1. Create local pre-update backup\n"
            "  2. Pull latest image\n"
            "  3. Restart containers\n"
            "  4. Verify service is running\n\n"
            "Continue?",
            "Update nginx Proxy Manager"
        ):
            return

        try:
            maint_mgr = self._get_maintenance_manager()

            self.ui.show_infobox("Updating nginx Proxy Manager...\n\nPlease wait...")

            success = maint_mgr.update_nginx(backup_first=True)

            if success:
                self.ui.show_success(
                    "nginx Proxy Manager updated successfully!\n\n"
                    "A local pre-update backup was created on disk.\n"
                    "Service is running with the latest version."
                )
                logger.info("nginx update completed via TUI")
            else:
                if self.ui.confirm_action(
                    "nginx update failed!\n\n"
                    "Do you want to rollback to the previous version?",
                    "Update Failed"
                ):
                    self.ui.show_infobox("Rolling back nginx...\n\nPlease wait...")
                    backup_path = maint_mgr.rollback_nginx()
                    if backup_path:
                        self.ui.show_success(f"Rollback successful!\n\nRestored from: {backup_path}")
                    else:
                        self.ui.show_error("Rollback failed. Check logs for details.")
                else:
                    self.ui.show_error("Update failed. Check logs for details.")

        except Exception as e:
            logger.error(f"nginx update error: {e}")
            self.ui.show_error(f"Update failed:\n\n{e}")

    def handle_update_mailcow(self):
        """Update Mailcow"""
        if not self.ui.confirm_action(
            "This will update Mailcow using the official update script.\n\n"
            "A local directory backup will be created on disk before the update.\n\n"
            "WARNING: This may take 10-20 minutes!\n\n"
            "The update process:\n"
            "  1. Create local pre-update backup\n"
            "  2. Run official update script\n"
            "  3. Restart services\n"
            "  4. Run database migrations\n\n"
            "Mailcow will be temporarily unavailable during the update.\n\n"
            "Continue?",
            "Update Mailcow"
        ):
            return

        try:
            maint_mgr = self._get_maintenance_manager()

            self.ui.show_infobox(
                "Updating Mailcow...\n\n"
                "This may take 10-20 minutes.\n"
                "Please be patient..."
            )

            success = maint_mgr.update_mailcow(backup_first=True)

            if success:
                self.ui.show_success(
                    "Mailcow updated successfully!\n\n"
                    "A local pre-update backup was created on disk.\n"
                    "All services have been restarted.\n"
                    "Check logs for detailed update information."
                )
                logger.info("Mailcow update completed via TUI")
            else:
                if self.ui.confirm_action(
                    "Mailcow update failed!\n\n"
                    "Do you want to rollback to the previous version?\n\n"
                    "Note: This rolls back config/compose files only.\n"
                    "Database migrations are not reversed.\n"
                    "For full data rollback, use Restore Management.",
                    "Update Failed"
                ):
                    self.ui.show_infobox("Rolling back Mailcow...\n\nPlease wait...")
                    backup_path = maint_mgr.rollback_mailcow()
                    if backup_path:
                        self.ui.show_success(f"Rollback successful!\n\nRestored from: {backup_path}")
                    else:
                        self.ui.show_error("Rollback failed. Check logs for details.")
                else:
                    self.ui.show_error(
                        "Update failed. Check logs for details.\n\n"
                        "You may need to restore from backup."
                    )

        except Exception as e:
            logger.error(f"Mailcow update error: {e}")
            self.ui.show_error(f"Update failed:\n\n{e}")

    def handle_update_system(self):
        """Update system packages"""
        # Show update type selection
        choices = [
            ("all", "All packages (full system upgrade)"),
            ("security", "Security updates only")
        ]

        code, update_type = self.ui.d.menu(
            "Select update type:\n\n"
            "Full upgrade may update kernel and require reboot.\n"
            "Security updates are safer for production systems.",
            title="System Update Type",
            choices=choices,
            width=60,
            height=12
        )

        if code != self.ui.d.OK:
            return

        security_only = (update_type == "security")

        if not self.ui.confirm_action(
            f"This will update system packages ({update_type}).\n\n"
            "The process includes:\n"
            "  • apt-get update\n"
            f"  • {'Security updates only' if security_only else 'Full package upgrade'}\n"
            "  • Remove unnecessary packages\n"
            "  • Clean package cache\n\n"
            "This may take 10-30 minutes.\n\n"
            "Continue?",
            "Update System"
        ):
            return

        try:
            maint_mgr = self._get_maintenance_manager()

            self.ui.show_infobox(
                "Updating system packages...\n\n"
                "This may take 10-30 minutes.\n"
                "Please be patient..."
            )

            success = maint_mgr.update_system_packages(security_only=security_only)

            if success:
                self.ui.show_success(
                    "System packages updated successfully!\n\n"
                    "Check if a reboot is required:\n"
                    "  • /var/run/reboot-required file exists\n"
                    "  • Kernel updated\n\n"
                    "To reboot: System Configuration → Reboot System"
                )
                logger.info(f"System update completed via TUI (security_only={security_only})")
            else:
                self.ui.show_error("System update failed. Check logs for details.")

        except Exception as e:
            logger.error(f"System update error: {e}")
            self.ui.show_error(f"Update failed:\n\n{e}")

    def handle_cleanup_docker(self):
        """Cleanup Docker"""
        if not self.ui.confirm_action(
            "This will cleanup unused Docker resources:\n\n"
            "  • Stopped containers\n"
            "  • Unused images\n"
            "  • Unused volumes\n"
            "  • Unused networks\n\n"
            "WARNING: This cannot be undone!\n\n"
            "Only resources not used by any container will be removed.\n\n"
            "Continue?",
            "Cleanup Docker"
        ):
            return

        try:
            maint_mgr = self._get_maintenance_manager()

            self.ui.show_infobox("Cleaning up Docker resources...\n\nPlease wait...")

            stats = maint_mgr.cleanup_docker()

            if stats['success']:
                self.ui.show_success(
                    "Docker cleanup completed!\n\n"
                    f"Space freed: {stats['space_freed']}\n\n"
                    "Removed:\n"
                    f"  • {stats['containers_removed']} stopped containers\n"
                    f"  • {stats['volumes_removed']} unused volumes\n"
                    f"  • Unused images\n"
                    f"  • Unused networks"
                )
                logger.info(f"Docker cleanup completed via TUI: {stats['space_freed']} freed")
            else:
                self.ui.show_error("Docker cleanup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Docker cleanup error: {e}")
            self.ui.show_error(f"Cleanup failed:\n\n{e}")

    def handle_cleanup_backups(self):
        """Cleanup old backups based on retention policy"""
        try:
            backup_mgr = self._get_backup_manager()
            if not backup_mgr:
                self.ui.show_error("Backup manager not available")
                return

            # Get current retention policy from config
            retention = backup_mgr.borg_config['retention']

            # Select service to cleanup
            services = [
                ("nginx", "nginx Proxy Manager"),
                ("mailcow", "Mailcow"),
                ("both", "Both services")
            ]

            selected = self.ui.select_from_list(
                services,
                "Select service to cleanup:",
                "Cleanup Old Backups"
            )

            if not selected:
                return

            # Confirm action
            if not self.ui.confirm_action(
                f"This will prune old remote Borg archives for {selected} using retention policy:\n\n"
                f"  • Daily: Keep last {retention['daily']} backups\n"
                f"  • Weekly: Keep last {retention['weekly']} backups\n"
                f"  • Monthly: Keep last {retention['monthly']} backups\n\n"
                "Archives on the remote rsync server older than these retention\n"
                "periods will be permanently deleted.\n\n"
                "Continue?",
                "Cleanup Old Backups"
            ):
                return

            # Show progress
            self.ui.show_infobox("Pruning old remote Borg archives...\n\nPlease wait...")

            # Determine which services to cleanup
            services_to_cleanup = []
            if selected == "both":
                services_to_cleanup = ["nginx", "mailcow"]
            else:
                services_to_cleanup = [selected]

            # Cleanup each service
            success_count = 0
            for service in services_to_cleanup:
                repo = backup_mgr._get_borg_repo(service)
                if not repo:
                    logger.error(f"No Borg repo configured for {service}")
                    continue
                if backup_mgr.prune_old_backups(repo):
                    success_count += 1
                    logger.info(f"Pruned old backups for {service}")
                else:
                    logger.error(f"Failed to prune backups for {service}")

            # Show result
            if success_count == len(services_to_cleanup):
                self.ui.show_success(
                    f"Remote backup cleanup completed successfully!\n\n"
                    f"Cleaned up {len(services_to_cleanup)} service(s) on remote rsync server.\n\n"
                    "Old Borg archives have been pruned based on retention policy.\n"
                    "Check logs for details about freed space."
                )
                logger.info(f"Backup cleanup completed via TUI for {services_to_cleanup}")
            else:
                self.ui.show_error(
                    f"Backup cleanup partially failed.\n\n"
                    f"Successfully cleaned: {success_count}/{len(services_to_cleanup)} services.\n\n"
                    "Check logs for details."
                )

        except Exception as e:
            logger.error(f"Backup cleanup error: {e}")
            self.ui.show_error(f"Cleanup failed:\n\n{e}")

    def handle_setup_gandi_domain(self):
        """Setup DNS zone for a Gandi domain"""
        # Get domain name from user
        domain = self.ui.input_text(
            "Enter the domain name to set up at Gandi:\n\n"
            "The domain must already be transferred to Gandi\n"
            "and added to Mailcow with DKIM keys generated.",
            "Setup Gandi Domain"
        )

        if not domain:
            return

        domain = domain.strip().lower()

        if not self.ui.confirm_action(
            f"This will set up the complete DNS zone for {domain} at Gandi.\n\n"
            "The setup process:\n"
            "  1. Verify prerequisites (Gandi, Mailcow, DKIM)\n"
            "  2. Create all DNS records (MX, SPF, DKIM, DMARC, etc.)\n"
            "  3. Activate Gandi LiveDNS nameservers\n"
            "  4. Enable DNSSEC\n"
            "  5. Verify records\n\n"
            "This will create ~17 DNS records and enable DNSSEC.\n\n"
            "Continue?",
            f"Setup Gandi Domain: {domain}"
        ):
            return

        try:
            self.ui.show_infobox(
                f"Setting up Gandi domain: {domain}\n\n"
                "This may take 30-60 seconds.\n"
                "Please wait..."
            )

            script = "/opt/server-manager/scripts/setup-gandi-domain.sh"
            returncode, stdout, stderr = run_command(
                ["bash", script, domain],
                check=False,
                timeout=120
            )

            # Combine output
            output = stdout
            if stderr:
                output += "\n--- stderr ---\n" + stderr

            if returncode == 0:
                self.ui.show_scrollable_text(
                    output,
                    f"Gandi Domain Setup: {domain} - Complete"
                )

                self.ui.show_info(
                    f"Domain {domain} has been set up at Gandi!\n\n"
                    "Manual steps remaining:\n\n"
                    f"  1. NPM: Request SSL cert for {domain}, mta-sts.{domain}\n"
                    "     (DNS challenge with Gandi credentials)\n\n"
                    f"  2. NPM: Create proxy hosts for {domain}\n"
                    f"     and mta-sts.{domain}\n\n"
                    "  3. Wait for DNS propagation (up to 48h)\n\n"
                    "  4. Test email delivery",
                    f"Setup Complete: {domain}"
                )
                logger.info(f"Gandi domain setup completed via TUI: {domain}")
            else:
                self.ui.show_scrollable_text(
                    output,
                    f"Gandi Domain Setup: {domain} - Failed"
                )
                logger.error(f"Gandi domain setup failed via TUI: {domain}")

        except Exception as e:
            logger.error(f"Gandi domain setup error: {e}")
            self.ui.show_error(f"Domain setup failed:\n\n{e}")
