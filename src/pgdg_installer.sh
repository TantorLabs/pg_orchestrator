#!/bin/bash

# pgdg_installer.sh
###################

# This script compiles and installs PostgreSQL from source,
# allows you to specify the maintenance version, sets up the postgres user,
# initializes the database cluster, and starts the PostgreSQL server.

# Usage:
#   sudo ./pgdg_installer.sh --maintenance-version=<version> [--install-path=<path>] [--initdb-only]
#   Or inside a container as root:
#   ./pgdg_installer.sh --maintenance-version=<version> [--install-path=<path>] [--initdb-only]

# Example:
#   sudo ./pgdg_installer.sh --maintenance-version=15.4 --install-path=/usr/local/pgsql
#   ./pgdg_installer.sh --initdb-only
# -----------------------------------------------------------------------------
# Author:     Lev Nikolaev
# Email:      lev.nikolaev@tantorlabs.com
# Created:    2025-03-24
# License:    MIT
# -----------------------------------------------------------------------------

set -e

# Script metadata
AUTHOR="Lev Nikolaev"
EMAIL="lev.nikolaev@tantorlabs.com"
CREATED_DATE="2025-03-24"

# Function to display usage instructions
usage() {
    echo "Usage: sudo $0 [--maintenance-version=<version>] [--install-path=<path>] [--initdb-only] [--with-initdb] [--from-file=<package_file>] [--version]"
    echo
    echo "Options:"
    echo "  --maintenance-version  Specify the maintenance version of PostgreSQL to install (e.g., 15.4)."
    echo "                         When installing from source, this is required."
    echo "  --install-path         Specify the installation path of PostgreSQL binaries."
    echo "                         When using --initdb-only, this must be provided."
    echo "  --initdb-only          Only perform initdb and start the PostgreSQL server using the specified INSTALL_PATH."
    echo "  --with-initdb          Perform initdb and start the PostgreSQL server after building and installing."
    echo "  --from-file=<file>     Install PostgreSQL from a pre-built package (.deb or .rpm)."
    echo "                         In this case, MAINTENANCE_VERSION and INSTALL_PATH are determined automatically."
    echo "  --version              Show script version and author info."
    echo
    exit 1
}


# Function to display version and author info
show_version() {
    echo "pgdg_installer.sh"
    echo "Author:  $AUTHOR"
    echo "Email:   $EMAIL"
    echo "Created: $CREATED_DATE"
    echo "License: MIT"
    exit 0
}

# Check for --version before any other logic
for arg in "$@"; do
    if [[ "$arg" == "--version" ]]; then
        show_version
    fi
done


INITDB_ONLY=false
WITH_INITDB=false

# Parse input parameters
for i in "$@"; do
    case $i in
        --maintenance-version=*)
            MAINTENANCE_VERSION="${i#*=}"
            ;;
        --install-path=*)
            INSTALL_PATH="${i#*=}"
            ;;
        --initdb-only)
            INITDB_ONLY=true
            ;;
        --with-initdb)
            WITH_INITDB=true
            ;;
        --from-file=*)
            ARG_FROM_FILE__="${i#*=}"
            ;;
        --version)
            show_version
            exit 0
            ;;
        *)
            usage
            ;;
    esac
done

if [ -z "$ARG_FROM_FILE__" ] && [ -z "$INSTALL_PATH" ]; then
    INSTALL_PATH="/usr/local/pgsql"
fi

# MAINTENANCE_VERSION from package
get_maintenance_version_from_package() {
    if [ ! -f "$ARG_FROM_FILE__" ]; then
        echo "Error: Package file $ARG_FROM_FILE__ does not exist." >&2
        exit 1
    fi

    file_extension="${ARG_FROM_FILE__##*.}"
    case "$file_extension" in
        deb)
            # For a deb package, use dpkg-deb --show, the output looks something like this:
            # postgresql-16   16.8-1.pgdg120+1
            pkg_info=$(dpkg-deb --show "$ARG_FROM_FILE__")
            pkg_name=$(echo "$pkg_info" | awk '{print $1}')
            pkg_version_full=$(echo "$pkg_info" | awk '{print $2}')
            # Извлекаем только часть до тире
            pkg_version=$(echo "$pkg_version_full" | cut -d'-' -f1)
            ;;
        rpm)
            # For rpm package we use rpm -qpi
            pkg_info=$(rpm -qpi "$ARG_FROM_FILE__")
            pkg_name=$(echo "$pkg_info" | grep -i '^Name' | awk -F: '{print $2}' | tr -d ' ')
            pkg_version=$(echo "$pkg_info" | grep -i '^Version' | awk -F: '{print $2}' | tr -d ' ')
            ;;
        *)
            echo "Error: Unsupported package extension '$file_extension'. Only deb and rpm are supported." >&2
            exit 1
            ;;
    esac

    # Restrict installation to official PostgreSQL packages only
    if ! echo "$pkg_name" | grep -qi "postgresql"; then
        echo "Error: The package $ARG_FROM_FILE__ does not appear to be an official PostgreSQL package." >&2
        exit 1
    fi

    echo "$pkg_version"
}


# If --from-file, get MAINTENANCE_VERSION from package
if [ -n "$ARG_FROM_FILE__" ]; then
    MAINTENANCE_VERSION=$(get_maintenance_version_from_package)
    echo "Determined MAINTENANCE_VERSION from package: $MAINTENANCE_VERSION"
fi

# Function to check if the specified version is available
check_version_available() {
    echo "Checking availability of PostgreSQL version ${MAINTENANCE_VERSION}..."
    # Get the list of available versions
    AVAILABLE_VERSIONS=$(curl -s https://ftp.postgresql.org/pub/source/ | grep -oP 'v\d+\.\d+(\.\d+)?/' | tr -d '/v')

    if echo "$AVAILABLE_VERSIONS" | grep -w "$MAINTENANCE_VERSION" > /dev/null; then
        echo "Version ${MAINTENANCE_VERSION} is available for download."
    else
        echo "PostgreSQL version ${MAINTENANCE_VERSION} is not available. Please check the version number."
        echo "Available versions (sorted):"
        echo "$AVAILABLE_VERSIONS" | tr ' ' '\n' | sort -Vr | less
        exit 1
    fi
}

# Determine OS information
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=$ID
    OS_VERSION_ID=$VERSION_ID
    OS_ARCH=$(uname -m)
    OS_INFO="${ID_LIKE} ${PRETTY_NAME}"
    OS_INFO=$(echo $OS_INFO | tr '[:upper:]' '[:lower:]')
else
    echo "Cannot determine operating system information."
    exit 1
fi

# Function to install dependencies
install_dependencies() {
    if [[ $OS_INFO == *"debian"* ]] || [[ $OS_INFO == *"ubuntu"* ]]; then
        export DEBIAN_FRONTEND=noninteractive
        echo "Installing build dependencies for Debian/Ubuntu..."
        apt-get update || true
        apt-get install -y build-essential libreadline-dev zlib1g-dev pkg-config libicu-dev flex bison libssl-dev libxml2-dev libxslt1-dev libcurl4-openssl-dev wget curl vim lsb-release || true
    elif [[ $OS_INFO == *"rhel"* ]] || [[ $OS_INFO == *"centos"* ]] || [[ $OS_INFO == *"fedora"* ]] || [[ $OS_INFO == *"oracle"* ]]; then
        echo "Installing build dependencies for RHEL/CentOS/Fedora..."
        if [ -x "$(command -v dnf)" ]; then
            PM="dnf"
        else
            PM="yum"
        fi
        $PM install -y gcc readline-devel zlib-devel pkg-config libicu-devel flex bison make openssl-devel libxml2-devel libxslt-devel curl-devel wget curl vim --skip-broken || true
    else
        echo "Unsupported operating system."
        exit 1
    fi
}

# Function to create the postgres user
prepare_postgres_user() {
    echo "Creating postgres user..."
    PG_USER_HOME="/var/lib/postgresql"

    if ! id -u postgres >/dev/null 2>&1; then
        getent group postgres >/dev/null || groupadd -r postgres
        getent passwd postgres >/dev/null || useradd -r -g postgres -d "$PG_USER_HOME" -s /bin/bash postgres
    else
        # Update the home directory if it's different
        current_home=$(getent passwd postgres | cut -d: -f6)
        if [ "$current_home" != "$PG_USER_HOME" ]; then
            usermod -d "$PG_USER_HOME" -m postgres
        fi
    fi

    mkdir -p "$PG_USER_HOME"
    chown postgres:postgres "$PG_USER_HOME"
    chmod 700 "$PG_USER_HOME"
    usermod -a -G $(whoami) postgres

    mkdir -p /var/run/postgresql
    chown -R postgres /var/run/postgresql

    # Add PostgreSQL bin directory to postgres user's PATH
    echo "Updating postgres user's PATH..."
    PROFILE_FILE="$PG_USER_HOME/.bashrc"
    if ! grep -q "$INSTALL_PATH/bin" "$PROFILE_FILE" 2>/dev/null; then
        echo "export PATH=\$PATH:$INSTALL_PATH/bin" >> "$PROFILE_FILE"
    fi
    chown postgres:postgres "$PROFILE_FILE"

    # Create .bash_profile for .bashrc
    BASH_PROFILE="$PG_USER_HOME/.bash_profile"
    if [ ! -f "$BASH_PROFILE" ]; then
        echo "if [ -f ~/.bashrc ]; then" > "$BASH_PROFILE"
        echo "    . ~/.bashrc" >> "$BASH_PROFILE"
        echo "fi" >> "$BASH_PROFILE"
    fi
    chown postgres:postgres "$BASH_PROFILE"
}

# Function to compile and install PostgreSQL
install_postgresql_from_source() {
    check_version_available

    echo "Downloading PostgreSQL source code version ${MAINTENANCE_VERSION}..."
    SOURCE_URL="https://ftp.postgresql.org/pub/source/v${MAINTENANCE_VERSION}/postgresql-${MAINTENANCE_VERSION}.tar.gz"

    # Create a temporary directory for the build process
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"

    # Download the source code
    wget "$SOURCE_URL" -O postgresql.tar.gz
    if [ $? -ne 0 ]; then
        echo "Failed to download PostgreSQL source code. Please check the version number."
        exit 1
    fi

    # Extract the source code
    tar -xzf postgresql.tar.gz
    cd postgresql-*

    # Configure, compile, and install
    ./configure --prefix="$INSTALL_PATH" --with-openssl --with-libxml --with-libxslt --with-icu
    make -j "$(nproc)"
    make install

    # Build and install contrib modules
    cd contrib
    make -j "$(nproc)" all
    make install

    # Return to the original directory and remove the temporary directory
    cd /
    rm -rf "$TEMP_DIR"

    # Create the postgres user
    prepare_postgres_user

    # Output the path to pg_config
    echo "PostgreSQL version ${MAINTENANCE_VERSION} has been installed in ${INSTALL_PATH}."
    echo "Binary files are located in: ${INSTALL_PATH}/bin/"
    echo "pg_config is located at: ${INSTALL_PATH}/bin/pg_config"
    echo "$INSTALL_PATH" > /tmp/pg_install_path.txt
    echo "INSTALL_PATH recorded in /tmp/pg_install_path.txt"
}

# Function to run commands as postgres user
run_as_postgres() {
    if [ "$(id -u)" -eq 0 ]; then
        # Running as root
        if command -v sudo >/dev/null 2>&1; then
            sudo -u postgres "$@"
        elif command -v su >/dev/null 2>&1; then
            su - postgres -c "$*"
        else
            # No sudo or su, attempt to run command directly (may not change user)
            echo "Warning: Cannot switch to postgres user. Attempting to run command as root."
            "$@"
        fi
    elif [ "$(id -nu)" = "postgres" ]; then
        # Already running as postgres user
        "$@"
    else
        echo "Error: Must be run as root or postgres user."
        exit 1
    fi
}

# Function to initialize the database cluster and start PostgreSQL
initialize_postgresql() {
    # Check if INSTALL_PATH is set
    if [ -z "$INSTALL_PATH" ]; then
        echo "Error: INSTALL_PATH is not set."
        exit 1
    fi

    # Preparing a postgres user (the prepare_postgres_user function already creates the user)
    if ! id postgres >/dev/null 2>&1; then
        echo "User 'postgres' does not exist. Creating user 'postgres'..."
        prepare_postgres_user  # Функция, которая создаёт пользователя postgres с нужными настройками
        echo "User 'postgres' created successfully."
    fi

    # Define MAINTENANCE_VERSION (use only the first two parts, e.g. 16.8)
    if [ -z "$MAINTENANCE_VERSION" ]; then
        if [ -x "$INSTALL_PATH/bin/pg_config" ]; then
            FULL_VERSION=$("$INSTALL_PATH/bin/pg_config" --version | awk '{print $2}')
            MAJOR_VERSION=$(echo "$FULL_VERSION" | cut -d. -f1,2)
        else
            echo "Error: Cannot determine PostgreSQL version. Please specify --maintenance-version or ensure PostgreSQL is installed."
            exit 1
        fi
    else
        MAJOR_VERSION=$(echo "$MAINTENANCE_VERSION" | cut -d. -f1,2)
    fi

    DATA_DIR="/var/lib/postgresql/${MAJOR_VERSION}/data"
    echo "Initializing PostgreSQL cluster in ${DATA_DIR}..."

    mkdir -p "$DATA_DIR"
    chown postgres:postgres "$DATA_DIR"
    chmod 700 "$DATA_DIR"

    # Run initdb with the full path, updating PATH for the postgres user
    run_as_postgres bash -c "export PATH=\$PATH:$INSTALL_PATH/bin; $INSTALL_PATH/bin/initdb -D '$DATA_DIR'"
}

install_from_file() {
    # Check if the package file exists
    if [ ! -f "$ARG_FROM_FILE__" ]; then
        echo "Error: Package file $ARG_FROM_FILE__ does not exist." >&2
        exit 1
    fi

    file_extension="${ARG_FROM_FILE__##*.}"
    case "$file_extension" in
        deb)
            # For a deb package, use dpkg-deb --show, the output looks something like this:
            # postgresql-16   16.8-1.pgdg120+1
            pkg_info=$(dpkg-deb --show "$ARG_FROM_FILE__")
            pkg_name=$(echo "$pkg_info" | awk '{print $1}')
            pkg_version_full=$(echo "$pkg_info" | awk '{print $2}')
            # Извлекаем только основную версию, например "16.8"
            pkg_version=$(echo "$pkg_version_full" | cut -d'-' -f1)
            ;;
        rpm)
            # For rpm package we use rpm -qpi
            pkg_info=$(rpm -qpi "$ARG_FROM_FILE__")
            pkg_name=$(echo "$pkg_info" | grep -i '^Name' | awk -F: '{print $2}' | tr -d ' ')
            pkg_version=$(echo "$pkg_info" | grep -i '^Version' | awk -F: '{print $2}' | tr -d ' ')
            ;;
        *)
            echo "Error: Unsupported package extension '$file_extension'. Only deb and rpm are supported." >&2
            exit 1
            ;;
    esac

    echo "Installing package $ARG_FROM_FILE__..."

    if [[ $OS_INFO == *"rhel"* ]] || [[ $OS_INFO == *"centos"* ]] || [[ $OS_INFO == *"fedora"* ]] || [[ $OS_INFO == *"oracle"* ]]; then
        if [ ! -f /etc/yum.repos.d/pgdg-redhat-all.repo ]; then
            echo "Adding PostgreSQL repository for RPM-based system..."
            if [[ $OS_INFO == *"fedora"* ]]; then
                if [ -x "$(command -v dnf)" ]; then
                    dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/pgdg-fedora-repo-latest.noarch.rpm
                else
                    yum install -y https://download.postgresql.org/pub/repos/yum/reporpms/pgdg-fedora-repo-latest.noarch.rpm
                fi
            else
                # For RHEL/CentOS/Oracle
                RHEL_VERSION=$(rpm -E %{rhel})
                if [ -x "$(command -v dnf)" ]; then
                    dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-${RHEL_VERSION}-x86_64/pgdg-redhat-repo-latest.noarch.rpm
                else
                    yum install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-${RHEL_VERSION}-x86_64/pgdg-redhat-repo-latest.noarch.rpm
                fi
            fi

            if [ -x "$(command -v dnf)" ]; then
                dnf makecache
            else
                yum makecache
            fi
        fi

        if [ -x "$(command -v dnf)" ]; then
            dnf install -y "$ARG_FROM_FILE__"
        else
            yum install -y "$ARG_FROM_FILE__"
        fi

    elif [[ $OS_INFO == *"debian"* ]] || [[ $OS_INFO == *"ubuntu"* ]]; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        if ! grep -q "^deb .*apt\.postgresql\.org" /etc/apt/sources.list /etc/apt/sources.list.d/*; then
            echo "Adding PostgreSQL repository for Debian/Ubuntu..."
            echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" | tee /etc/apt/sources.list.d/pgdg.list
            wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
            apt-get update
        fi

        echo "Installing package from file: $ARG_FROM_FILE__..."
        # Используем apt для установки локального deb-пакета с автоматическим разрешением зависимостей
        apt install -y "$ARG_FROM_FILE__"
    else
        echo "Unsupported OS. Cannot install package from file."
        exit 1
    fi

    # Override INSTALL_PATH based on package type and extracted version
    MAJOR_VERSION=$(echo "$pkg_version" | cut -d. -f1)
    if [ "$file_extension" = "deb" ]; then
        INSTALL_PATH="/usr/lib/postgresql/${MAJOR_VERSION}"
    elif [ "$file_extension" = "rpm" ]; then
        INSTALL_PATH="/usr/pgsql-${MAJOR_VERSION}"
    fi
    echo "Updated INSTALL_PATH to: $INSTALL_PATH"

    # Write INSTALL_PATH to a file in /tmp
    INSTALL_PATH_FILE="/tmp/pg_install_path_${MAJOR_VERSION}.txt"
    echo "$INSTALL_PATH" > "$INSTALL_PATH_FILE"
    echo "INSTALL_PATH recorded in $INSTALL_PATH_FILE"
}

# Entry Point
if [ "$INITDB_ONLY" = true ]; then
    initialize_postgresql
    LOG_FILE="$DATA_DIR/postgresql.log"
    echo "Starting PostgreSQL server..."
    run_as_postgres bash -c "export PATH=\$PATH:${INSTALL_PATH}/bin && ${INSTALL_PATH}/bin/pg_ctl -D '$DATA_DIR' -l '$LOG_FILE' start"
    echo "PostgreSQL server has been started."
else
    if [ -z "$MAINTENANCE_VERSION" ]; then
        echo "Error: Maintenance version not specified."
        usage
    fi

    install_dependencies

    if [ -n "$ARG_FROM_FILE__" ]; then
        echo "Installing PostgreSQL from package file: $ARG_FROM_FILE__"
        install_from_file
    else
        echo "Installing PostgreSQL from source..."
        install_postgresql_from_source
    fi

    if [ "$WITH_INITDB" = true ]; then
        initialize_postgresql
    fi
fi