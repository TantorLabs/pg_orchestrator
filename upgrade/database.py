import os
import re
import shlex
from dataclasses import dataclass

from typing import Optional
from manager.dockerManager import DockerContainerManager
from src.logger import logger, TIMESTAMP


@dataclass
class DbVersion:
    """Structure representing the database version."""
    version: str
    edition: Optional[str]
    major: str
    db_type: str

    def __str__(self):
        if self.db_type == 'ttdb':
            return f'{self.version}-{self.edition}'
        else:  # pgdg
            return f'{self.version}-pgdg'

    @staticmethod
    def create(version: str, edition: Optional[str] = None, db_type: str = 'ttdb') -> 'DbVersion':
        """
         - For ttdb waiting to get 'MAJOR.MINOR.PATCH', with edition.
         - For pgdg get X.Y of version. edition doesn't require.
        """
        if db_type == 'ttdb':
            if not re.match(r'^\d+\.\d+\.\d+$', version):
                raise ValueError(f'Invalid version string "{version}" - must be in MAJOR.MINOR.PATCH form for ttdb')
            if not edition:
                raise ValueError(f'DB edition is not provided for version "{version}" in ttdb mode')
            major = version.split('.')[0]
            return DbVersion(version, edition, major, db_type)

        elif db_type == 'pgdg':
            # "MAJOR.MINOR" or "MAJOR.MINOR.PATCH",
            # but we save only "MAJOR.MINOR" for pgdg_installer.sh
            pattern = re.match(r'^(\d+)\.(\d+)(\.\d+)?$', version)
            if not pattern:
                raise ValueError(f'Invalid pgdg version string "{version}". Expected at least MAJOR.MINOR (e.g. "16.6" or "16.6.0")')
            major_part = pattern.group(1)  # e.g. "16"
            minor_part = pattern.group(2)  # e.g. "6"
            version = f'{major_part}.{minor_part}'  # e.g. "16.6"
            return DbVersion(version, None, major_part, db_type)

        else:
            raise ValueError(f'Unknown db_type "{db_type}"')

@dataclass
class Database:
    """Structure for storing database information."""
    version: DbVersion
    bin_path: str
    data_path: str
    logs_dir: str
    docker_manager: DockerContainerManager

@dataclass
class NexusEnv:
    """Structure for storing Nexus settings."""
    NEXUS_USER: str
    NEXUS_USER_PASSWORD: str
    NEXUS_URL: str

    @staticmethod
    def from_env(db_type) -> 'NexusEnv':
        # Load Nexus environment variables
        keys = ['NEXUS_USER', 'NEXUS_USER_PASSWORD', 'NEXUS_URL']
        env_vars = {}
        for key in keys:
            value = os.environ.get(key)
            if not value and db_type == 'ttdb':
                raise KeyError(f'Nexus setting {key} not set in environment variables')
            env_vars[key] = value
        return NexusEnv(**env_vars)

def get_pg_binary(db: Database, binary: str):
    # Get the path to a PostgreSQL binary
    return os.path.join(db.bin_path, binary)

def get_log_file(db: Database, logfilename: str):
    # Get the full path to a log file
    return os.path.join(db.logs_dir, logfilename)

def run_pg_binary(db: Database, binary: str, *args: str):
    # Run a PostgreSQL binary with specified arguments
    logfilename = f'{binary}_{db.version}.log'
    logfile = get_log_file(db, logfilename)
    command = shlex.join([
        get_pg_binary(db, binary),
        *args
    ])
    logger.debug('Executing: %s', command)
    try:
        _, output = db.docker_manager.shell(
            "su", "-", "postgres", "-c", command,
            logfile=logfile,
            cwd=db.data_path
        )
        return output
    except Exception as e:
        logger.warning('Failed to execute %s. See errors in logfile: %s', binary, logfile)
        # If pg_upgrade we have to see additional logs
        if binary == 'pg_upgrade':
            error_logs_dir = os.path.join(db.logs_dir, 'additionally_errors_logs')
            db.docker_manager.shell('mkdir', '-p', error_logs_dir)
            db.docker_manager.shell('bash', '-c', f'cp -r {db.data_path}/pg_upgrade_output.d/*/log/* {error_logs_dir}')
            db.docker_manager.shell('find', error_logs_dir, '-type', 'd', '-exec', 'chmod', '775', '{}', '+')
            db.docker_manager.shell('find', error_logs_dir, '-type', 'f', '-exec', 'chmod', '664', '{}', '+')
        raise


def initdb(db: Database, *args: str):
    """Initialize the database cluster."""
    run_pg_binary(db, 'initdb', '-D', db.data_path, *args)

def pg_ctl(db: Database, command: str, *args: str):
    """Control the database cluster using pg_ctl."""
    run_pg_binary(db, 'pg_ctl', '-D', db.data_path, command, *args)

def run_db(db: Database):
    """Start the database."""
    logger.info('Starting PostgreSQL (%s)', db.version)
    pg_ctl(db, 'start')

def stop_db(db: Database):
    """Stop the database."""
    logger.info('Stopping PostgreSQL (%s)', db.version)
    pg_ctl(db, 'stop')

def run_sql_script(db: Database, script_path: str):
    """Run a SQL script fully and then check its log for errors."""
    logger.info('Running SQL script %s (%s)', script_path, db.version)
    binary = 'psql'
    logfilename = f'{binary}_{db.version}.log'
    logfile = get_log_file(db, logfilename)

    # Running psql without ON_ERROR_STOP=1, because we have to see any ERROR
    run_pg_binary(db, binary, '-f', script_path)

    if os.path.exists(logfile):
        with open(logfile, 'r', encoding='utf-8') as f:
            for line in f:
                if 'ERROR:' in line:
                    logger.error('Error found in SQL script execution log: %s', line.strip())
                    raise RuntimeError(f'Error found during execution of {script_path}. See {logfile} for details.')
    else:
        logger.warning('Logfile %s not found for analysis', logfile)

def run_shell_script(db: Database, script: str):
    """Run a shell script."""
    # script_name = os.path.splitext(script)[0]
    script_name = os.path.splitext(os.path.basename(script))[0]
    logfilename = get_log_file(db, f'shell_{script_name}.log')
    logger.debug('Executing shell script: %s', script)
    db.docker_manager.shell('bash', script,
                            cwd=db.bin_path,
                            logfile=logfilename,
                            env={
                                'DB_PATH': db.data_path
                            })

def pg_upgrade(new_db: Database, old_db: Database):
    """Perform pg_upgrade to update the database."""
    logger.info('Running pg_upgrade from %s to %s', old_db.version, new_db.version)
    new_db.docker_manager.shell('cp',f'{old_db.data_path}/postgresql.conf',f'{new_db.data_path}')
    result = run_pg_binary(new_db, 'pg_upgrade',
                           '-b', old_db.bin_path,
                           '-B', new_db.bin_path,
                           '-d', old_db.data_path,
                           '-D', new_db.data_path)
    script = 'update_extensions.sql'
    if script in result:
        logger.info('Running %s script to update extensions', script)
        run_db(new_db)
        run_sql_script(new_db, script)
        stop_db(new_db)

def pg_dumpall(db: Database, dump_file: str):
    """Create a dump of the entire database."""
    logger.info('Running pg_dumpall (%s)', db.version)
    run_pg_binary(db, 'pg_dumpall', '-f', dump_file)

def get_bin_dir(docker_manager: DockerContainerManager, version: DbVersion, package_path: Optional[str] = None) -> str:
    """
    Get the binary directory path for a specified version
    ttdb: /opt/tantor/db/{version.major}/bin
    pgdg: /usr/local/pgsql/{version.major}/bin
    """
    if version.db_type == 'ttdb':
        logger.info(f'Installation path for {version.db_type}:{version.version} is /opt/tantor/db/{version.major}/bin')
        return f'/opt/tantor/db/{version.major}/bin'
    elif version.db_type == 'pgdg':
        if package_path:
            file_path = f"/tmp/pg_install_path_{version.major}.txt"
            try:
                result = docker_manager.shell("cat", file_path, check_code=False)
                if result.exit_code == 0:
                    install_path = result.output.strip()
                    if install_path:
                        logger.info(
                            f'Installation path for {version.db_type}:{version.version} is {install_path}')
                        return os.path.join(install_path, "bin")
            except Exception as e:
                logger.warning("Error reading install path from %s: %s", file_path, e)
        # If package not exists return default path
        return f'/usr/local/pgsql/{version.major}/bin'
    else:
        raise ValueError(f"Unsupported db_type: {version.db_type}")

def verify_package_version(docker_manager: DockerContainerManager, package_path: str, version: DbVersion):
    """Verifies that the package version matches the expected version."""
    logger.info('Verifying package version for %s', package_path)
    cmd = ['dpkg', '-I', package_path]
    result = docker_manager.shell(*cmd, check_code=False)
    if result.exit_code != 0:
        raise RuntimeError(f'Failed to inspect package {package_path}')

    output = result.output
    # Search for the line with Version
    match = re.search(r'Version:\s*(\S+)', output)
    if not match:
        raise RuntimeError(f'Failed to parse version from package {package_path}')

    package_version = match.group(1)
    if version.db_type == 'pgdg':
        # For pgdg-packages exclude version number before the first '-'
        pkg_ver_numeric = package_version.split('-')[0]
        if pkg_ver_numeric != version.version:
            raise RuntimeError(f'Package version {package_version} does not match expected version {version.version}')
    else:
        # For ttdb check version directly
        if package_version != version.version:
            raise RuntimeError(f'Package version {package_version} does not match expected version {version.version}')

def run_db_installer(docker_manager: DockerContainerManager, db_installer: str,
                     pgdg_installer: str,
                     version: DbVersion, db_logs_dir: str, nexus_env: NexusEnv,
                     package_path: Optional[str], db_type: str) -> None:
    """Runs db_installer.sh or pgdg_installer.sh depending on db_type."""
    logfilename = os.path.join(db_logs_dir, f'{db_type}_installer_{version}.log')
    if db_type == 'pgdg':
        if package_path:
            logger.info('Running pgdg_installer for %s (from package)', version)
            # Now install from package working only for debian!
            verify_package_version(docker_manager, package_path, version)
            command = [
                pgdg_installer,
                f'--from-file={package_path}'
            ]
            env_vars = None
        else:
            logger.info('Running pgdg_installer for %s', version)
            command = [
                pgdg_installer,
                f'--maintenance-version={version.version}',
                f'--install-path=/usr/local/pgsql/{version.major}'
            ]
            env_vars = None
    else:
        # db_type == 'ttdb'
        if package_path:
            logger.info('Running db_installer for %s (from package)', version)
            # When package is specified, only use --from-file
            # Verify package version
            verify_package_version(docker_manager, package_path, version)

            command = [
                db_installer,
                f'--from-file={package_path}'
            ]
            env_vars = {"DEBIAN_FRONTEND": "noninteractive"}
        else:
            logger.info('Running db_installer for %s', version)
            # If package is not specified, use Nexus
            command = [
                db_installer,
                f'--edition={version.edition}',
                f'--maintenance-version={version.version}',
                f'--major-version={version.major}'
            ]
            env_vars = nexus_env.__dict__

    try:
        docker_manager.shell(
            *command,
            logfile=logfilename,
            env=env_vars
        )
    except Exception as e:
        logger.error('Failed to execute installer. See log in %s', logfilename)
        raise

def create_db(docker_manager: DockerContainerManager, db_installer: str, logs_dir: str,
              db_path: str, version: DbVersion, nexus_env: NexusEnv, db_type: str,
              pgdg_installer: str, package_path: Optional[str] = None) -> Database:
    """Create and install a database of the specified version."""
    # Create a log directory for the specified database version
    db_logs_dir = os.path.join(logs_dir, f'logs_{version}')
    os.makedirs(db_logs_dir, exist_ok=True)


    # Run db_installer only for install ttdb or pgdg
    run_db_installer(docker_manager, db_installer, pgdg_installer, version, db_logs_dir, nexus_env, package_path, db_type)
    bin_path = get_bin_dir(docker_manager, version, package_path)
    return Database(version, bin_path, db_path, db_logs_dir, docker_manager)