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
from lib.config import ConfigError

LOG_FILE = "/opt/server-manager/logs/server-manager.log"

SERVICES = ["nginx", "mailcow", "mailcow-directory", "server-manager", "monitoring-stack", "credentials"]

# Service name -> manager method (backup_mailcow's backup_type defaults to "all")
BACKUP_METHODS = {s: f"backup_{s.replace('-', '_')}" for s in SERVICES}
RESTORE_METHODS = {s: f"restore_{s.replace('-', '_')}" for s in SERVICES}


def get_log_tail(lines: int = 15) -> str:
    """Return the last N lines of the application log for failure notifications."""
    try:
        with open(LOG_FILE, 'r') as f:
            return ''.join(f.readlines()[-lines:])
    except Exception:
        return ''


def cmd_backup(args):
    """Run a backup for the specified service."""
    service = args.service
    verify = args.verify

    backup_mgr = BackupManager()
    notif_mgr = NotificationManager()

    start_time = datetime.now()

    try:
        method = BACKUP_METHODS.get(service)
        if method is None:
            print(f"Error: Unknown service: {service}")
            sys.exit(1)
        success = getattr(backup_mgr, method)(verify=verify)

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
            error_msg = backup_mgr.last_error or 'Backup operation returned false (no error recorded)'
            print(f"Backup failed: {error_msg}")
            details = {'error': error_msg, 'duration': f"{duration:.2f} seconds"}
            log_tail = get_log_tail()
            if log_tail:
                details['output'] = f"Last {log_tail.count(chr(10))} log lines from {LOG_FILE}:\n{log_tail}"
            try:
                notif_mgr.send_backup_notification(service, False, details)
            except Exception as ne:
                print(f"Warning: Failed to send failure notification: {ne}")
            sys.exit(1)

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        print(f"Backup error: {e}")
        details = {'error': str(e), 'duration': f"{duration:.2f} seconds"}
        log_tail = get_log_tail()
        if log_tail:
            details['output'] = f"Last {log_tail.count(chr(10))} log lines from {LOG_FILE}:\n{log_tail}"
        try:
            notif_mgr.send_backup_notification(service, False, details)
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
        method = RESTORE_METHODS.get(service)
        if method is None:
            print(f"Error: Unknown service: {service}")
            sys.exit(1)
        success = getattr(restore_mgr, method)(backup_name=archive)

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


def cmd_check(args):
    """Run borg check on backup repositories."""
    service = args.service

    backup_mgr = BackupManager()
    notif_mgr = NotificationManager()

    start_time = datetime.now()

    if service == "all":
        print("Checking integrity of all Borg repositories (this can take a while)...")
        results = backup_mgr.check_all_repositories(timeout=args.timeout)
    else:
        print(f"Checking integrity of {service} repository...")
        results = {service: backup_mgr.check_repository(service, timeout=args.timeout)}

    duration = (datetime.now() - start_time).total_seconds()

    failed = [s for s, ok in results.items() if not ok]
    for svc, ok in results.items():
        print(f"  [{'OK' if ok else 'FAILED'}] {svc}")
    print(f"\n{len(results) - len(failed)}/{len(results)} repositories OK ({duration:.0f}s)")

    if failed:
        error_msg = backup_mgr.last_error or f"borg check failed for: {', '.join(failed)}"
        details = {
            'failed_repositories': ', '.join(failed),
            'error': error_msg,
            'duration': f"{duration:.0f} seconds",
        }
        log_tail = get_log_tail()
        if log_tail:
            details['log_tail'] = f"\n{log_tail}"
        try:
            notif_mgr.send_maintenance_notification("Borg Repository Check", False, details)
        except Exception as ne:
            print(f"Warning: Failed to send failure notification: {ne}")
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

        files_removed = stats.get('files_removed', 0)
        print(f"\nCleanup completed:")
        print(f"  Directories removed: {stats['backups_removed']}")
        print(f"  Files removed: {files_removed}")
        print(f"  Space freed: {size_str}")

        if stats['backups_removed'] > 0 or files_removed > 0:
            notif_mgr.send_maintenance_notification(
                "Backup Cleanup",
                stats['success'],
                {
                    'directories_removed': stats['backups_removed'],
                    'files_removed': files_removed,
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
        choices=SERVICES,
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
        choices=SERVICES,
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

    # check subcommand
    check_parser = subparsers.add_parser(
        "check", help="Verify Borg repository integrity (borg check)"
    )
    check_parser.add_argument(
        "service", nargs="?", default="all",
        choices=["all"] + SERVICES,
        help="Repository to check (default: all)"
    )
    check_parser.add_argument(
        "--timeout", type=int, default=3600,
        help="Per-repository timeout in seconds (default: 3600)"
    )
    check_parser.set_defaults(func=cmd_check)

    # cleanup subcommand
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
    cleanup_parser.add_argument(
        "--retention-days", type=int, default=30,
        help="Days to retain backups (default: 30)"
    )
    cleanup_parser.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    try:
        args.func(args)
    except ConfigError as e:
        print(f"Configuration error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
