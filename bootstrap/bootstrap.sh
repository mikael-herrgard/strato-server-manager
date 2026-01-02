#!/bin/bash
################################################################################
# Server Manager - Bootstrap Installation Script
#
# This script automates the complete installation of Server Manager on a fresh
# VPS or server. It handles system packages, Python environment, configuration,
# and creates all necessary directories and symlinks.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash
#
# Or directly:
#   ./bootstrap.sh
#
# Environment Variables:
#   GITHUB_REPO   - Git repository URL (default: https://github.com/USER/server-manager.git)
#   GITHUB_BRANCH - Git branch to clone (default: main)
#   SKIP_CONFIRM  - Skip confirmation prompts (default: false)
#
################################################################################

set -e
set -o pipefail

################################################################################
# Configuration Variables
################################################################################

VERSION="1.0.0"
INSTALL_DIR="/opt/server-manager"
VENV_DIR="${INSTALL_DIR}/venv"
CONFIG_DIR="${INSTALL_DIR}/config"
LOG_DIR="${INSTALL_DIR}/logs"
STATE_DIR="${INSTALL_DIR}/state"
BACKUP_STAGING="/var/backups/local"
SYMLINK_PATH="/usr/local/bin/server-manager"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/USER/server-manager.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
LOG_FILE="/tmp/server-manager-bootstrap-$(date +%Y%m%d-%H%M%S).log"
SKIP_CONFIRM="${SKIP_CONFIRM:-false}"

################################################################################
# Color codes for output
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

################################################################################
# Utility Functions
################################################################################

log() {
    echo -e "${CYAN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✓${NC} $*" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}✗ ERROR:${NC} $*" | tee -a "$LOG_FILE" >&2
}

warn() {
    echo -e "${YELLOW}⚠ WARNING:${NC} $*" | tee -a "$LOG_FILE"
}

step() {
    echo "" | tee -a "$LOG_FILE"
    echo -e "${BOLD}${BLUE}==>${NC} ${BOLD}$*${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
}

prompt() {
    local prompt_text="$1"
    local default_value="$2"
    local result

    if [ -n "$default_value" ]; then
        read -p "$(echo -e "${CYAN}?${NC} ${prompt_text} [${default_value}]: ")" result
        result="${result:-$default_value}"
    else
        read -p "$(echo -e "${CYAN}?${NC} ${prompt_text}: ")" result
    fi

    echo "$result"
}

prompt_yes_no() {
    local prompt_text="$1"
    local default="${2:-y}"
    local result

    if [ "$default" = "y" ]; then
        read -p "$(echo -e "${CYAN}?${NC} ${prompt_text} [Y/n]: ")" result
        result="${result:-y}"
    else
        read -p "$(echo -e "${CYAN}?${NC} ${prompt_text} [y/N]: ")" result
        result="${result:-n}"
    fi

    [[ "$result" =~ ^[Yy] ]]
}

check_command() {
    command -v "$1" &>/dev/null
}

cleanup_on_error() {
    error "Installation failed! Check log file: $LOG_FILE"
    exit 1
}

trap cleanup_on_error ERR

################################################################################
# Pre-flight Checks
################################################################################

preflight_checks() {
    step "Running pre-flight checks"

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        error "This script must be run as root"
        echo "Please run: sudo $0"
        exit 1
    fi
    success "Running as root"

    # Check OS compatibility
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
            error "This script only supports Ubuntu and Debian"
            exit 1
        fi
        success "OS compatible: $PRETTY_NAME"
    else
        error "Cannot determine OS type"
        exit 1
    fi

    # Check disk space (minimum 10GB)
    local available_space=$(df / | awk 'NR==2 {print $4}')
    if [ "$available_space" -lt 10485760 ]; then
        warn "Less than 10GB free disk space available"
    else
        success "Sufficient disk space available"
    fi

    # Check internet connectivity
    if ! curl -fsSL --connect-timeout 5 https://github.com >/dev/null 2>&1; then
        error "No internet connectivity detected"
        exit 1
    fi
    success "Internet connectivity confirmed"

    # Check Python version
    if check_command python3; then
        local python_version=$(python3 --version 2>&1 | awk '{print $2}')
        local python_major=$(echo "$python_version" | cut -d. -f1)
        local python_minor=$(echo "$python_version" | cut -d. -f2)

        if [ "$python_major" -ge 3 ] && [ "$python_minor" -ge 9 ]; then
            success "Python version acceptable: $python_version"
        else
            warn "Python version $python_version detected (minimum 3.9 recommended)"
        fi
    else
        log "Python3 not found (will be installed)"
    fi
}

################################################################################
# System Package Installation
################################################################################

install_system_packages() {
    step "Installing system packages"

    log "Updating package lists..."
    apt-get update -qq >> "$LOG_FILE" 2>&1
    success "Package lists updated"

    log "Installing required packages..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        dialog \
        borgbackup \
        rsync \
        docker.io \
        docker-compose \
        ufw \
        git \
        python3 \
        python3-venv \
        python3-pip \
        curl \
        openssh-client \
        ca-certificates >> "$LOG_FILE" 2>&1

    success "All required packages installed"

    # Start and enable Docker
    log "Starting Docker service..."
    systemctl start docker >> "$LOG_FILE" 2>&1
    systemctl enable docker >> "$LOG_FILE" 2>&1
    success "Docker service started and enabled"
}

################################################################################
# Application Download
################################################################################

download_application() {
    step "Downloading Server Manager application"

    # Check if directory already exists
    if [ -d "$INSTALL_DIR" ]; then
        warn "Installation directory already exists: $INSTALL_DIR"

        if [ "$SKIP_CONFIRM" = "false" ]; then
            if prompt_yes_no "Remove existing installation and continue?" "n"; then
                log "Removing existing installation..."
                rm -rf "$INSTALL_DIR"
                success "Existing installation removed"
            else
                error "Installation cancelled by user"
                exit 1
            fi
        else
            log "Removing existing installation (SKIP_CONFIRM=true)..."
            rm -rf "$INSTALL_DIR"
        fi
    fi

    log "Cloning repository from: $GITHUB_REPO (branch: $GITHUB_BRANCH)"
    git clone --branch "$GITHUB_BRANCH" --depth 1 "$GITHUB_REPO" "$INSTALL_DIR" >> "$LOG_FILE" 2>&1

    if [ ! -d "$INSTALL_DIR" ] || [ ! -f "$INSTALL_DIR/server_manager.py" ]; then
        error "Failed to clone repository or main file missing"
        exit 1
    fi

    success "Application downloaded successfully"
}

################################################################################
# Python Environment Setup
################################################################################

setup_python_environment() {
    step "Setting up Python virtual environment"

    log "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1
    success "Virtual environment created"

    log "Upgrading pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1
    success "Pip upgraded"

    log "Installing Python dependencies..."
    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" >> "$LOG_FILE" 2>&1
        success "Python dependencies installed"
    else
        error "requirements.txt not found"
        exit 1
    fi

    # Verify critical imports
    log "Verifying Python modules..."
    "$VENV_DIR/bin/python3" -c "import dialog; import yaml; import paramiko; import docker" >> "$LOG_FILE" 2>&1
    success "Python modules verified"
}

################################################################################
# Configuration Setup
################################################################################

setup_configuration() {
    step "Setting up configuration template"

    log "Copying configuration template..."

    if [ -f "$CONFIG_DIR/settings.yaml.example" ]; then
        cp "$CONFIG_DIR/settings.yaml.example" "$CONFIG_DIR/settings.yaml"
        success "Configuration template created"
    else
        error "Configuration template not found"
        exit 1
    fi
}

################################################################################
# Directory Structure
################################################################################

create_directory_structure() {
    step "Creating directory structure"

    log "Creating required directories..."
    mkdir -p "$LOG_DIR" "$STATE_DIR" "$BACKUP_STAGING"

    chmod 755 "$LOG_DIR" "$STATE_DIR" "$BACKUP_STAGING"

    success "Directory structure created"
}

################################################################################
# Symlink and Permissions
################################################################################

setup_symlink() {
    step "Setting up symlink and permissions"

    log "Making server_manager.py executable..."
    chmod +x "$INSTALL_DIR/server_manager.py"
    success "Executable permission set"

    log "Creating symlink..."
    ln -sf "$INSTALL_DIR/server_manager.py" "$SYMLINK_PATH"
    success "Symlink created: $SYMLINK_PATH"

    # Make scripts executable
    if [ -d "$INSTALL_DIR/scripts" ]; then
        log "Making scripts executable..."
        chmod +x "$INSTALL_DIR/scripts"/*.sh 2>/dev/null || true
        success "Scripts made executable"
    fi
}

################################################################################
# Verification
################################################################################

verify_installation() {
    step "Verifying installation"

    local errors=0

    # Check executable exists
    if [ -f "$INSTALL_DIR/server_manager.py" ] && [ -x "$INSTALL_DIR/server_manager.py" ]; then
        success "Main executable exists and is executable"
    else
        error "Main executable not found or not executable"
        errors=$((errors + 1))
    fi

    # Check symlink
    if [ -L "$SYMLINK_PATH" ] && [ -e "$SYMLINK_PATH" ]; then
        success "Symlink exists and is valid"
    else
        error "Symlink not found or invalid"
        errors=$((errors + 1))
    fi

    # Check venv
    if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
        success "Virtual environment exists"
    else
        error "Virtual environment not found"
        errors=$((errors + 1))
    fi

    # Check configuration
    if [ -f "$CONFIG_DIR/settings.yaml" ]; then
        success "Configuration file exists"
    else
        error "Configuration file not found"
        errors=$((errors + 1))
    fi

    # Check directories
    for dir in "$LOG_DIR" "$STATE_DIR" "$BACKUP_STAGING"; do
        if [ -d "$dir" ]; then
            success "Directory exists: $dir"
        else
            error "Directory not found: $dir"
            errors=$((errors + 1))
        fi
    done

    # Test Python import
    if "$VENV_DIR/bin/python3" -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); import server_manager" >> "$LOG_FILE" 2>&1; then
        success "Python module can be imported"
    else
        warn "Python module import test failed (may require configuration)"
    fi

    if [ $errors -gt 0 ]; then
        error "Installation verification failed with $errors errors"
        exit 1
    fi
}

################################################################################
# Completion Message
################################################################################

show_completion_message() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}${BOLD}Server Manager installation completed successfully!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${BOLD}Next steps:${NC}"
    echo ""
    echo "  ${YELLOW}1.${NC} Set up credentials (if not already done):"
    echo "     See: $INSTALL_DIR/CREDENTIALS_SETUP.md"
    echo ""
    echo "  ${YELLOW}2.${NC} Edit configuration file:"
    echo -e "     ${CYAN}nano $CONFIG_DIR/settings.yaml${NC}"
    echo ""
    echo "  ${YELLOW}3.${NC} Run Server Manager:"
    echo -e "     ${CYAN}server-manager${NC}"
    echo ""
    echo "  ${YELLOW}4.${NC} From the TUI:"
    echo "     - Install Docker"
    echo "     - Install nginx"
    echo "     - Restore nginx from backup"
    echo "     - Install Mailcow"
    echo "     - Restore Mailcow from backup"

    echo ""
    echo -e "${BOLD}Additional information:${NC}"
    echo "  Installation directory: $INSTALL_DIR"
    echo "  Command: server-manager"
    echo "  Configuration: $CONFIG_DIR/settings.yaml"
    echo "  Log file: $LOG_FILE"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

################################################################################
# Main Execution
################################################################################

main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BOLD}Server Manager Bootstrap Installer${NC}"
    echo -e "Version: $VERSION"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    log "Starting installation process..."
    log "Log file: $LOG_FILE"
    echo ""

    # Execute installation steps
    preflight_checks
    install_system_packages
    download_application
    setup_python_environment
    create_directory_structure
    setup_configuration
    setup_symlink
    verify_installation

    # Show completion message
    show_completion_message

    log "Installation completed successfully"
}

# Run main function
main "$@"
