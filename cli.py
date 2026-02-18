#!/usr/bin/env python3
"""
Server Manager CLI
Entry point for automated backup, restore, and cleanup operations.
"""

import argparse
import sys
import os
from datetime import datetime

# Ensure the server-manager root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.backup import BackupManager
from lib.restore import RestoreManager
from lib.maintenance import MaintenanceManager
from lib.notifications import NotificationManager


def cmd_backup(args):
    """Run a backup for the specified service."""
    service = args.service
    verify = args.verify

    backup_mgr = BackupManager()
    notif_mgr = NotificationManager()

    start_time = datetime.now()

    try:
        if service == "nginx":
            success = backup_mgr.backup_nginx(verify=verify)
        elif service == "mailcow":
            success = backup_mgr.backup_mailcow(backup_type="all", verify=verify)
        elif service == "mailcow-directory":
            success = backup_mgr.backup_mailcow_directory(verify=verify)
        elif service == "server-manager":
            success = backup_mgr.backup_server_manager(verify=verify)
        elif service == "monitoring-stack":
            success = backup_mgr.backup_monitoring_stack(verify=verify)
        else:
            print(f"Error: Unknown service: {service}")
            sys.exit(1)

        duration = (datetime.now() - start_time).total_seconds()

        if success:
            print(f"Backup completed successfully in {duration:.2f} seconds")
            try:
                notif_mgr.send_backup_notification(
                    service, True,
                    {'duration': f"{duration:.2f} seconds", 'verified': verify}
                )
            except Exception as ne:
                print(f"Warning: Failed to send success notification: {ne}")
        else:
            print("Backup failed")
            try:
                notif_mgr.send_backup_notification(
                    service, False,
                    {'error': 'Backup operation returned false', 'duration': f"{duration:.2f} seconds"}
                )
            except Exception as ne:
                print(f"Warning: Failed to send failure notification: {ne}")
            sys.exit(1)

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        print(f"Backup error: {e}")
        try:
            notif_mgr.send_backup_notification(
                service, False,
                {'error': str(e), 'duration': f"{duration:.2f} seconds"}
            )
        except Exception as ne:
            print(f"Warning: Failed to send error notification: {ne}")
        sys.exit(1)


def cmd_restore(args):
    """Restore a service from a Borg backup."""
    service = args.service
    archive = args.archive

    restore_mgr = RestoreManager()

    # List mode — show available backups and exit
    if args.list:
        print(f"Available backups for {service}:")
        backups = restore_mgr.list_remote_backups(service)
        if not backups:
            print("  No backups found.")
            sys.exit(1)
        for b in backups:
            print(f"  {b['name']}")
        sys.exit(0)

    # Confirmation prompt (skip with --yes)
    backup_label = archive if archive else "latest"
    if not args.yes:
        print(f"About to restore {service} from backup: {backup_label}")
        print("This will stop the service, replace its data, and restart it.")
        answer = input("Continue? [y/N] ").strip().lower()
        if answer != 'y':
            print("Restore cancelled.")
            sys.exit(0)

    start_time = datetime.now()

    try:
        if service == "nginx":
            success = restore_mgr.restore_nginx(backup_name=archive)
        elif service == "mailcow":
            success = restore_mgr.restore_mailcow(backup_name=archive)
        elif service == "mailcow-directory":
            success = restore_mgr.restore_mailcow_directory(backup_name=archive)
        elif service == "server-manager":
            success = restore_mgr.restore_server_manager(backup_name=archive)
        elif service == "monitoring-stack":
            success = restore_mgr.restore_monitoring_stack(backup_name=archive)
        else:
            print(f"Error: Unknown service: {service}")
            sys.exit(1)

        duration = (datetime.now() - start_time).total_seconds()

        if success:
            print(f"Restore completed successfully in {duration:.2f} seconds")
        else:
            print("Restore failed — check logs at /opt/server-manager/logs/server-manager.log")
            sys.exit(1)

    except Exception as e:
        print(f"Restore error: {e}")
        sys.exit(1)


RESTORE_ORDER = [
    ('server-manager',    'restore_server_manager'),
    ('nginx',             'restore_nginx'),
    ('mailcow-directory', 'restore_mailcow_directory'),
    ('mailcow',           'restore_mailcow'),
    ('monitoring-stack',  'restore_monitoring_stack'),
]


def cmd_restore_all(args):
    """Restore all services from latest backups in DR order."""
    restore_mgr = RestoreManager()

    # Confirmation prompt
    if not args.yes:
        print("Full restore will restore ALL services in this order:")
        for i, (service, _) in enumerate(RESTORE_ORDER, 1):
            print(f"  {i}. {service}")
        print("")
        print("Each service will be restored from its latest backup.")
        print("This will stop and restart services as needed.")
        answer = input("\nContinue? [y/N] ").strip().lower()
        if answer != 'y':
            print("Restore cancelled.")
            sys.exit(0)

    total_start = datetime.now()
    results = []

    for service, method_name in RESTORE_ORDER:
        print(f"\n{'='*60}")
        print(f"Restoring {service}...")
        print(f"{'='*60}")

        start_time = datetime.now()

        try:
            method = getattr(restore_mgr, method_name)
            success = method(backup_name="latest")
            duration = (datetime.now() - start_time).total_seconds()

            if success:
                print(f"  {service}: OK ({duration:.1f}s)")
                results.append((service, True, duration, None))
            else:
                print(f"  {service}: FAILED ({duration:.1f}s)")
                results.append((service, False, duration, "Restore returned false"))
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            print(f"  {service}: ERROR — {e}")
            results.append((service, False, duration, str(e)))

    # Summary
    total_duration = (datetime.now() - total_start).total_seconds()
    succeeded = sum(1 for _, ok, _, _ in results if ok)
    failed = len(results) - succeeded

    print(f"\n{'='*60}")
    print(f"Full Restore Summary ({total_duration:.1f}s total)")
    print(f"{'='*60}")
    for service, ok, duration, error in results:
        status = "OK" if ok else f"FAILED: {error}"
        print(f"  {service:25s} {duration:7.1f}s  {status}")
    print(f"\n  {succeeded} succeeded, {failed} failed")

    if failed > 0:
        print("\nCheck logs: /opt/server-manager/logs/server-manager.log")
        sys.exit(1)


def cmd_cleanup(args):
    """Clean up old pre-update, pre-restore, and rollback directories."""
    retention_days = args.retention_days

    maintenance_mgr = MaintenanceManager()
    notif_mgr = NotificationManager()

    print(f"Cleaning up backup directories older than {retention_days} days...")

    try:
        stats = maintenance_mgr.cleanup_old_backups(keep_days=retention_days)

        if stats['space_freed_mb'] >= 1024:
            size_str = f"{stats['space_freed_mb'] / 1024:.2f} GB"
        else:
            size_str = f"{stats['space_freed_mb']:.1f} MB"

        print(f"\nCleanup completed:")
        print(f"  Directories removed: {stats['backups_removed']}")
        print(f"  Space freed: {size_str}")

        if stats['backups_removed'] > 0:
            notif_mgr.send_maintenance_notification(
                "Backup Cleanup",
                stats['success'],
                {
                    'directories_removed': stats['backups_removed'],
                    'space_freed': size_str,
                    'retention_days': retention_days,
                }
            )

        sys.exit(0 if stats['success'] else 1)

    except Exception as e:
        print(f"Cleanup error: {e}")
        notif_mgr.send_maintenance_notification(
            "Backup Cleanup", False, {'error': str(e)}
        )
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Server Manager CLI for backup, restore, and cleanup operations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # backup subcommand
    backup_parser = subparsers.add_parser("backup", help="Run a backup")
    backup_parser.add_argument(
        "service",
        choices=["nginx", "mailcow", "mailcow-directory", "server-manager", "monitoring-stack"],
        help="Service to back up"
    )
    backup_parser.add_argument(
        "--verify", action="store_true", default=False,
        help="Verify backup after creation"
    )
    backup_parser.set_defaults(func=cmd_backup)

    # restore subcommand
    restore_parser = subparsers.add_parser("restore", help="Restore a service from backup")
    restore_parser.add_argument(
        "service",
        choices=["nginx", "mailcow", "mailcow-directory", "server-manager", "monitoring-stack"],
        help="Service to restore"
    )
    restore_parser.add_argument(
        "--archive", default="latest",
        help="Archive name to restore (default: latest)"
    )
    restore_parser.add_argument(
        "--list", action="store_true", default=False,
        help="List available backups and exit"
    )
    restore_parser.add_argument(
        "--yes", "-y", action="store_true", default=False,
        help="Skip confirmation prompt"
    )
    restore_parser.set_defaults(func=cmd_restore)

    # restore-all subcommand
    restore_all_parser = subparsers.add_parser(
        "restore-all", help="Restore all services from latest backups (full DR)"
    )
    restore_all_parser.add_argument(
        "--yes", "-y", action="store_true", default=False,
        help="Skip confirmation prompt"
    )
    restore_all_parser.set_defaults(func=cmd_restore_all)

    # cleanup subcommand
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
    cleanup_parser.add_argument(
        "--retention-days", type=int, default=30,
        help="Days to retain backups (default: 30)"
    )
    cleanup_parser.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
