#!/bin/bash
# Mailcow DR Testing Sandbox Manager
# This script helps create a sandbox environment for testing disaster recovery
# without affecting your production Mailcow installation.

set -e

# Configuration
MAILCOW_DIR="/opt/mailcow-dockerized"
BACKUP_SUFFIX="backup-$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${MAILCOW_DIR}.${BACKUP_SUFFIX}"
STATE_FILE="/var/tmp/mailcow-sandbox-state"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_mailcow_exists() {
    if [[ ! -d "$MAILCOW_DIR" ]]; then
        log_error "Mailcow directory not found: $MAILCOW_DIR"
        exit 1
    fi
}

get_disk_space() {
    df -BG /opt | awk 'NR==2 {print $4}' | sed 's/G//'
}

check_disk_space() {
    local available=$(get_disk_space)
    local mailcow_size=$(du -sm "$MAILCOW_DIR" 2>/dev/null | awk '{print $1}')
    local required=$((mailcow_size * 2 / 1024 + 5))  # 2x size + 5GB buffer

    log_info "Disk space check:"
    log_info "  Available: ${available}GB"
    log_info "  Mailcow size: ${mailcow_size}MB (~$((mailcow_size / 1024))GB)"
    log_info "  Required: ~${required}GB"

    if [[ $available -lt $required ]]; then
        log_error "Insufficient disk space!"
        log_error "Need at least ${required}GB, but only ${available}GB available"
        return 1
    fi

    log_success "Disk space sufficient"
    return 0
}

save_state() {
    local backup_dir="$1"
    echo "BACKUP_DIR=$backup_dir" > "$STATE_FILE"
    echo "TIMESTAMP=$(date +%s)" >> "$STATE_FILE"
    log_info "State saved to $STATE_FILE"
}

load_state() {
    if [[ ! -f "$STATE_FILE" ]]; then
        log_error "No sandbox state found. Have you created a sandbox?"
        return 1
    fi
    source "$STATE_FILE"
    return 0
}

clear_state() {
    rm -f "$STATE_FILE"
    log_info "State cleared"
}

show_status() {
    echo ""
    echo "=========================================="
    echo "  MAILCOW DR SANDBOX STATUS"
    echo "=========================================="
    echo ""

    # Check if production Mailcow exists
    if [[ -d "$MAILCOW_DIR" ]]; then
        log_info "Current Mailcow: $MAILCOW_DIR"
        if docker compose -f "$MAILCOW_DIR/docker-compose.yml" ps --services 2>/dev/null | grep -q .; then
            echo -n "  Status: "
            if docker compose -f "$MAILCOW_DIR/docker-compose.yml" ps 2>/dev/null | grep -q "Up"; then
                echo -e "${GREEN}RUNNING${NC}"
            else
                echo -e "${YELLOW}STOPPED${NC}"
            fi
        else
            echo "  Status: No containers"
        fi
    else
        log_warning "No Mailcow found at $MAILCOW_DIR"
    fi

    echo ""

    # Check for backups
    local backups=($(ls -d ${MAILCOW_DIR}.backup-* 2>/dev/null || true))
    if [[ ${#backups[@]} -gt 0 ]]; then
        log_info "Backup directories found:"
        for backup in "${backups[@]}"; do
            local size=$(du -sh "$backup" 2>/dev/null | awk '{print $1}')
            echo "  - $(basename $backup) (${size})"
        done
    else
        log_info "No backup directories found"
    fi

    echo ""

    # Check sandbox state
    if [[ -f "$STATE_FILE" ]]; then
        load_state
        log_info "Sandbox state: ACTIVE"
        log_info "  Backup: $BACKUP_DIR"
        local backup_time=$(date -d @$TIMESTAMP '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r $TIMESTAMP '+%Y-%m-%d %H:%M:%S')
        log_info "  Created: $backup_time"
    else
        log_info "Sandbox state: INACTIVE"
    fi

    echo ""

    # Check Docker volumes
    local volumes=$(docker volume ls -q | grep -c "mailcowdockerized" 2>/dev/null || echo "0")
    log_info "Docker volumes: $volumes mailcow volumes found"

    echo ""
    echo "=========================================="
}

create_sandbox() {
    log_info "Creating DR testing sandbox..."
    echo ""

    # Safety checks
    check_mailcow_exists

    # Check if sandbox already exists
    if [[ -f "$STATE_FILE" ]]; then
        log_error "Sandbox already exists!"
        log_error "Run './$(basename $0) status' to see current state"
        log_error "Run './$(basename $0) revert' to revert first, or './$(basename $0) cleanup' to clean up"
        exit 1
    fi

    # Check disk space
    if ! check_disk_space; then
        exit 1
    fi

    echo ""
    log_warning "This will:"
    log_warning "  1. Stop all Mailcow services"
    log_warning "  2. Rename $MAILCOW_DIR to $BACKUP_DIR"
    log_warning "  3. Keep Docker volumes as-is (they won't interfere)"
    echo ""
    read -p "Continue? (yes/no): " confirm

    if [[ "$confirm" != "yes" ]]; then
        log_info "Aborted by user"
        exit 0
    fi

    echo ""

    # Step 1: Stop Mailcow
    log_info "Step 1/3: Stopping Mailcow services..."
    cd "$MAILCOW_DIR"
    if docker compose ps --services 2>/dev/null | grep -q .; then
        docker compose down
        log_success "Mailcow services stopped"
    else
        log_info "No running services found"
    fi

    echo ""

    # Step 2: Rename directory
    log_info "Step 2/3: Renaming Mailcow directory..."
    mv "$MAILCOW_DIR" "$BACKUP_DIR"
    log_success "Renamed: $MAILCOW_DIR -> $BACKUP_DIR"

    echo ""

    # Step 3: Save state
    log_info "Step 3/3: Saving sandbox state..."
    save_state "$BACKUP_DIR"

    echo ""
    log_success "=========================================="
    log_success "  SANDBOX CREATED SUCCESSFULLY!"
    log_success "=========================================="
    echo ""
    log_info "Your original Mailcow is safely backed up at:"
    log_info "  $BACKUP_DIR"
    echo ""
    log_info "Next steps:"
    log_info "  1. Test DR restore via TUI:"
    log_info "     /opt/server-manager/server_manager.py"
    log_info "     -> Restore Management -> Restore Mailcow Directory"
    echo ""
    log_info "  2. After directory restore, pull images:"
    log_info "     cd /opt/mailcow-dockerized && docker compose pull"
    log_info "     docker compose up -d && docker compose down"
    echo ""
    log_info "  3. Restore data via TUI:"
    log_info "     -> Restore Management -> Restore Mailcow Data"
    echo ""
    log_info "  4. Start and test:"
    log_info "     cd /opt/mailcow-dockerized && docker compose up -d"
    echo ""
    log_info "When done testing:"
    log_info "  - Success: Run './$(basename $0) cleanup' to remove backup"
    log_info "  - Failed:  Run './$(basename $0) revert' to restore original"
    echo ""
}

revert_sandbox() {
    log_info "Reverting to original Mailcow installation..."
    echo ""

    # Load state
    if ! load_state; then
        exit 1
    fi

    # Check if backup exists
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        log_error "Cannot revert!"
        exit 1
    fi

    echo ""
    log_warning "This will:"
    log_warning "  1. Stop any running Mailcow services"
    log_warning "  2. Remove current $MAILCOW_DIR"
    log_warning "  3. Restore $BACKUP_DIR"
    log_warning "  4. Restart original Mailcow services"
    echo ""
    read -p "Continue? (yes/no): " confirm

    if [[ "$confirm" != "yes" ]]; then
        log_info "Aborted by user"
        exit 0
    fi

    echo ""

    # Step 1: Stop current services
    log_info "Step 1/4: Stopping current services..."
    if [[ -d "$MAILCOW_DIR" ]]; then
        cd "$MAILCOW_DIR"
        if docker compose ps --services 2>/dev/null | grep -q .; then
            docker compose down
            log_success "Services stopped"
        else
            log_info "No running services"
        fi
        cd /
    fi

    echo ""

    # Step 2: Remove current directory
    log_info "Step 2/4: Removing test installation..."
    if [[ -d "$MAILCOW_DIR" ]]; then
        rm -rf "$MAILCOW_DIR"
        log_success "Test installation removed"
    else
        log_info "No test installation found"
    fi

    echo ""

    # Step 3: Restore original
    log_info "Step 3/4: Restoring original installation..."
    mv "$BACKUP_DIR" "$MAILCOW_DIR"
    log_success "Original installation restored"

    echo ""

    # Step 4: Start services
    log_info "Step 4/4: Starting Mailcow services..."
    cd "$MAILCOW_DIR"
    docker compose up -d
    log_success "Services started"

    # Clear state
    clear_state

    echo ""
    log_success "=========================================="
    log_success "  REVERTED TO ORIGINAL SUCCESSFULLY!"
    log_success "=========================================="
    echo ""
    log_info "Your original Mailcow is now running again"
    echo ""
    log_info "Verify services:"
    log_info "  cd $MAILCOW_DIR && docker compose ps"
    echo ""
}

cleanup_sandbox() {
    log_info "Cleaning up sandbox backup..."
    echo ""

    # Load state
    if ! load_state; then
        # No active sandbox, but maybe old backups exist
        log_warning "No active sandbox state found"
        log_info "Checking for old backup directories..."

        local backups=($(ls -d ${MAILCOW_DIR}.backup-* 2>/dev/null || true))
        if [[ ${#backups[@]} -eq 0 ]]; then
            log_info "No backup directories found"
            exit 0
        fi

        echo ""
        log_info "Found ${#backups[@]} backup directories:"
        for backup in "${backups[@]}"; do
            local size=$(du -sh "$backup" 2>/dev/null | awk '{print $1}')
            echo "  - $(basename $backup) (${size})"
        done
        echo ""

        read -p "Delete all backup directories? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Aborted by user"
            exit 0
        fi

        for backup in "${backups[@]}"; do
            log_info "Removing: $backup"
            rm -rf "$backup"
        done

        log_success "All backup directories removed"
        exit 0
    fi

    # Check if backup exists
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_warning "Backup directory not found: $BACKUP_DIR"
        log_info "It may have already been removed"
        clear_state
        exit 0
    fi

    # Verify current Mailcow is running
    if [[ ! -d "$MAILCOW_DIR" ]]; then
        log_error "Current Mailcow not found at $MAILCOW_DIR"
        log_error "Something went wrong! Use 'revert' to restore backup"
        exit 1
    fi

    echo ""
    log_warning "This will permanently delete the backup:"
    log_warning "  $BACKUP_DIR"
    echo ""
    log_warning "Make sure your current Mailcow is working properly first!"
    echo ""
    read -p "Delete backup? (yes/no): " confirm

    if [[ "$confirm" != "yes" ]]; then
        log_info "Aborted by user"
        exit 0
    fi

    echo ""
    log_info "Removing backup directory..."
    rm -rf "$BACKUP_DIR"
    log_success "Backup removed"

    # Clear state
    clear_state

    echo ""
    log_success "Cleanup complete!"
    echo ""
}

show_help() {
    cat << EOF
Mailcow DR Testing Sandbox Manager

Usage: $(basename $0) [command]

Commands:
  create    Create a sandbox environment for DR testing
            - Stops Mailcow services
            - Renames directory to .backup-TIMESTAMP
            - Prepares for DR restore testing

  revert    Revert to original Mailcow installation
            - Stops test installation
            - Removes test directory
            - Restores original from backup
            - Starts original services

  cleanup   Remove backup after successful DR test
            - Deletes backup directory
            - Clears sandbox state
            - Use after confirming DR test worked

  status    Show current sandbox status
            - Shows active installations
            - Lists backup directories
            - Shows sandbox state

  help      Show this help message

Examples:
  # Create sandbox for testing
  $(basename $0) create

  # Check status
  $(basename $0) status

  # After successful DR test
  $(basename $0) cleanup

  # If DR test failed, revert
  $(basename $0) revert

Workflow:
  1. $(basename $0) create
  2. Test DR restore via TUI
  3. If successful: $(basename $0) cleanup
     If failed:    $(basename $0) revert

EOF
}

# Main
check_root

case "${1:-}" in
    create)
        create_sandbox
        ;;
    revert)
        revert_sandbox
        ;;
    cleanup)
        cleanup_sandbox
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: ${1:-}"
        echo ""
        show_help
        exit 1
        ;;
esac
