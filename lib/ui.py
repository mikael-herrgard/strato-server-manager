"""
User Interface Module
TUI interface using dialog for raspi-config style menus
"""

import sys
from typing import List, Tuple, Optional, Callable
from .utils import logger

try:
    from dialog import Dialog
except ImportError:
    print("Error: pythondialog not installed")
    print("Please install: pip3 install pythondialog")
    sys.exit(1)


class ServerManagerUI:
    """TUI interface for server manager"""

    def __init__(self, title: str = "Server Manager"):
        """
        Initialize UI

        Args:
            title: Application title
        """
        self.title = title
        self.d = Dialog(dialog="dialog", autowidgetsize=True)
        self.d.add_persistent_args(['--keep-tite'])
        self.d.set_background_title(f"{title} v1.0")

        # UI dimensions
        self.height = 20
        self.width = 70
        self.menu_height = 12

    def show_main_menu(self) -> str:
        """
        Show main menu

        Returns:
            Selected menu code or 'exit'
        """
        menu_items = [
            ("1", "Backup Management"),
            ("2", "Restore Management"),
            ("3", "Installation"),
            ("4", "System Configuration"),
            ("5", "Maintenance"),
            ("6", "Status & Monitoring"),
            ("7", "Scheduling & Automation"),
            ("8", "Settings"),
            ("0", "Exit")
        ]

        code, tag = self.d.menu(
            "Main Menu - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title=self.title
        )

        if code == self.d.OK:
            return tag
        else:
            return "exit"

    def show_backup_menu(self) -> str:
        """
        Show backup management menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Backup nginx Proxy Manager"),
            ("2", "Backup Mailcow"),
            ("3", "View Backup Status"),
            ("4", "Configure Backup Schedule"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Backup Management - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Backup Management"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_restore_menu(self) -> str:
        """
        Show restore management menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Restore nginx Proxy Manager"),
            ("2", "Restore Mailcow"),
            ("3", "List Available Backups"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Restore Management - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Restore Management"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_installation_menu(self) -> str:
        """
        Show installation menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Install Docker"),
            ("2", "Install nginx Proxy Manager"),
            ("3", "Install Mailcow"),
            ("4", "Install Portainer"),
            ("5", "Check Prerequisites"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Installation - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Installation"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_system_menu(self) -> str:
        """
        Show system configuration menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Disable IPv6"),
            ("2", "Enable IPv6"),
            ("3", "System Information"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "System Configuration - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="System Configuration"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_maintenance_menu(self) -> str:
        """
        Show maintenance menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Update nginx Proxy Manager"),
            ("2", "Update Mailcow"),
            ("3", "Update System Packages"),
            ("4", "Cleanup Docker"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Maintenance - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Maintenance"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_monitoring_menu(self) -> str:
        """
        Show status & monitoring menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Service Status"),
            ("2", "Disk Usage"),
            ("3", "Container Stats"),
            ("4", "View Logs"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Status & Monitoring - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Status & Monitoring"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_settings_menu(self) -> str:
        """
        Show settings menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "Notification Settings"),
            ("2", "View Configuration"),
            ("3", "Edit Configuration File"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Settings - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Settings"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def show_scheduling_menu(self) -> str:
        """
        Show scheduling & automation menu

        Returns:
            Selected menu code or 'back'
        """
        menu_items = [
            ("1", "View Scheduled Tasks"),
            ("2", "Schedule Backup"),
            ("3", "Schedule Cleanup"),
            ("4", "Remove Schedule"),
            ("5", "Configure Notifications"),
            ("6", "Test Notification"),
            ("7", "Notification Status"),
            ("0", "Back to Main Menu")
        ]

        code, tag = self.d.menu(
            "Scheduling & Automation - Select an option:",
            height=self.height,
            width=self.width,
            menu_height=len(menu_items),
            choices=menu_items,
            title="Scheduling & Automation"
        )

        if code == self.d.OK:
            return tag
        else:
            return "back"

    def confirm_action(self, message: str, title: str = "Confirm") -> bool:
        """
        Show confirmation dialog

        Args:
            message: Confirmation message
            title: Dialog title

        Returns:
            True if user confirmed
        """
        code = self.d.yesno(
            message,
            height=10,
            width=self.width,
            title=title
        )

        return code == self.d.OK

    def show_message(
        self,
        message: str,
        title: str = "Information",
        msg_type: str = "info"
    ) -> None:
        """
        Show message dialog

        Args:
            message: Message to display
            title: Dialog title
            msg_type: Message type (info, error, warning, success)
        """
        if msg_type == "error":
            title = f"ERROR - {title}"
        elif msg_type == "warning":
            title = f"WARNING - {title}"
        elif msg_type == "success":
            title = f"SUCCESS - {title}"

        self.d.msgbox(
            message,
            height=15,
            width=self.width,
            title=title
        )

    def show_info(self, message: str, title: str = "Information") -> None:
        """Show information message"""
        self.show_message(message, title, "info")

    def show_error(self, message: str, title: str = "Error") -> None:
        """Show error message"""
        self.show_message(message, title, "error")

    def show_warning(self, message: str, title: str = "Warning") -> None:
        """Show warning message"""
        self.show_message(message, title, "warning")

    def show_success(self, message: str, title: str = "Success") -> None:
        """Show success message"""
        self.show_message(message, title, "success")

    def show_progress(
        self,
        title: str,
        text: str,
        percent: int = 0,
        width: int = 70
    ):
        """
        Show progress gauge

        Args:
            title: Dialog title
            text: Progress text
            percent: Progress percentage (0-100)
            width: Dialog width

        Note: This returns a gauge object that needs to be updated
        """
        return self.d.gauge_start(
            text,
            title=title,
            percent=percent,
            width=width
        )

    def select_from_list(
        self,
        items: List[Tuple[str, str]],
        title: str = "Select Item",
        text: str = "Choose an item:"
    ) -> Optional[str]:
        """
        Show selection menu

        Args:
            items: List of (tag, description) tuples
            title: Dialog title
            text: Dialog text

        Returns:
            Selected tag or None if cancelled
        """
        if not items:
            self.show_error("No items available", "Error")
            return None

        code, tag = self.d.menu(
            text,
            height=self.height,
            width=self.width,
            menu_height=min(len(items), 10),
            choices=items,
            title=title
        )

        if code == self.d.OK:
            return tag
        else:
            return None

    def select_backup(self, backups: List[str], service: str) -> Optional[str]:
        """
        Show backup selection menu

        Args:
            backups: List of backup names
            service: Service name (nginx, mailcow, etc.)

        Returns:
            Selected backup name or None
        """
        if not backups:
            self.show_error(f"No backups found for {service}", "No Backups")
            return None

        # Create menu items with latest first
        items = []
        for i, backup in enumerate(backups):
            if i == 0:
                items.append((backup, f"{backup} (LATEST)"))
            else:
                items.append((backup, backup))

        return self.select_from_list(
            items,
            title=f"Select {service} Backup",
            text="Choose a backup to restore:"
        )

    def input_text(
        self,
        prompt: str,
        title: str = "Input",
        init: str = "",
        password: bool = False
    ) -> Optional[str]:
        """
        Show text input dialog

        Args:
            prompt: Input prompt
            title: Dialog title
            init: Initial value
            password: If True, hide input

        Returns:
            User input or None if cancelled
        """
        if password:
            code, text = self.d.passwordbox(
                prompt,
                height=10,
                width=self.width,
                title=title,
                init=init
            )
        else:
            code, text = self.d.inputbox(
                prompt,
                height=10,
                width=self.width,
                title=title,
                init=init
            )

        if code == self.d.OK:
            return text
        else:
            return None

    def show_text_file(self, filepath: str, title: str = "File Viewer") -> None:
        """
        Show text file contents

        Args:
            filepath: Path to file
            title: Dialog title
        """
        try:
            self.d.textbox(
                filepath,
                height=self.height,
                width=self.width,
                title=title
            )
        except Exception as e:
            self.show_error(f"Error viewing file: {e}", "Error")

    def show_scrollable_text(
        self,
        text: str,
        title: str = "Information",
        height: int = 20,
        width: int = 70
    ) -> None:
        """
        Show scrollable text

        Args:
            text: Text to display
            title: Dialog title
            height: Dialog height
            width: Dialog width
        """
        self.d.scrollbox(
            text,
            height=height,
            width=width,
            title=title
        )

    def show_checklist(
        self,
        items: List[Tuple[str, str, bool]],
        title: str = "Select Items",
        text: str = "Choose items:"
    ) -> Optional[List[str]]:
        """
        Show checklist dialog

        Args:
            items: List of (tag, description, selected) tuples
            title: Dialog title
            text: Dialog text

        Returns:
            List of selected tags or None if cancelled
        """
        code, tags = self.d.checklist(
            text,
            height=self.height,
            width=self.width,
            list_height=min(len(items), 8),
            choices=items,
            title=title
        )

        if code == self.d.OK:
            return tags
        else:
            return None

    def show_radiolist(
        self,
        items: List[Tuple[str, str, bool]],
        title: str = "Select Option",
        text: str = "Choose an option:"
    ) -> Optional[str]:
        """
        Show radiolist dialog

        Args:
            items: List of (tag, description, selected) tuples
            title: Dialog title
            text: Dialog text

        Returns:
            Selected tag or None if cancelled
        """
        code, tag = self.d.radiolist(
            text,
            height=self.height,
            width=self.width,
            list_height=min(len(items), 8),
            choices=items,
            title=title
        )

        if code == self.d.OK:
            return tag
        else:
            return None

    def show_infobox(self, text: str, title: str = "Please Wait") -> None:
        """
        Show non-blocking info box (for status messages)

        Args:
            text: Text to display
            title: Dialog title
        """
        self.d.infobox(
            text,
            height=8,
            width=self.width,
            title=title
        )

    def pause(self, text: str, seconds: int = 5, title: str = "Please Wait") -> None:
        """
        Show pause dialog with countdown

        Args:
            text: Text to display
            seconds: Seconds to wait
            title: Dialog title
        """
        self.d.pause(
            text,
            height=8,
            width=self.width,
            seconds=seconds,
            title=title
        )


class ProgressTracker:
    """Track progress for long-running operations"""

    def __init__(self, ui: ServerManagerUI, title: str, steps: List[str]):
        """
        Initialize progress tracker

        Args:
            ui: UI instance
            title: Operation title
            steps: List of step descriptions
        """
        self.ui = ui
        self.title = title
        self.steps = steps
        self.current_step = 0
        self.total_steps = len(steps)
        self.gauge = None

    def start(self):
        """Start progress tracking"""
        if self.total_steps > 0:
            text = f"Step 1/{self.total_steps}: {self.steps[0]}"
            self.gauge = self.ui.show_progress(
                self.title,
                text,
                percent=0
            )

    def update(self, step: int, message: str = None):
        """
        Update progress

        Args:
            step: Current step number (0-indexed)
            message: Optional custom message
        """
        self.current_step = step

        if self.total_steps == 0:
            return

        percent = int((step / self.total_steps) * 100)

        if message:
            text = message
        elif step < self.total_steps:
            text = f"Step {step + 1}/{self.total_steps}: {self.steps[step]}"
        else:
            text = "Completed"

        if self.gauge:
            self.gauge.update(percent, text)

    def complete(self):
        """Complete progress tracking"""
        if self.gauge:
            self.gauge.update(100, "Completed")
            import time
            time.sleep(1)  # Show completion briefly
        self.stop()

    def stop(self):
        """Stop progress tracking"""
        if self.gauge:
            self.d = self.ui.d
            self.d.gauge_stop()
            self.gauge = None
