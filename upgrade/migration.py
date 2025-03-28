import os
import shlex
from dataclasses import dataclass
from typing import List, Optional

from upgrade.database import *
from manager.dockerManager import DockerContainerManager
from src.manifest import MigrationManifest, MigrationStep, MigrationStrategy, ScriptList
from src.logger import logger, TIMESTAMP

@dataclass
class Environment:
    tmp_dir: str
    new_db: str
    old_db: str
    logs_dir: str
    scripts_dir: str
    packages_dir: str
    db_installer: str
    pgdg_installer: str

    def get_script(self, script_name: str) -> str:
        # Get the absolute path of the specified script
        path = os.path.join(self.scripts_dir, script_name)
        if not os.path.isfile(path):
            raise FileNotFoundError(f'Failed to find script {path}')
        return os.path.abspath(path)

    def get_package(self, package_name: str) -> str:
        path = os.path.join(self.packages_dir, package_name)
        if not os.path.isfile(path):
            raise FileNotFoundError(f'Failed to find package {path}')
        return os.path.abspath(path)

    def get_temp_filename(self, filename: str) -> str:
        # Return the absolute path of a temporary file
        return os.path.join(self.tmp_dir, filename)

class MigrationRunner:
    def __init__(self, manifest: MigrationManifest, docker_manager: DockerContainerManager, env: Environment):
        self.manifest = manifest
        self.docker_manager = docker_manager
        self.env = env
        self.nexus_env = NexusEnv.from_env(self.manifest.db_type)
        self.db_installer = env.db_installer
        self.state = None  # Will be initialized in create_initial_state()

    def run_migration(self):
        # Main method to execute the migration process
        self.create_initial_state()     # TODO: PRE and POST SCRIPTS ACTIVATED
        for step in self.manifest.steps:
            self.prepare_step(step)
            self.run_step()

    def create_initial_state(self):
        # Initialize the initial database state
        logger.info('Creating initial database')
        initial_version = DbVersion.create(self.manifest.db_version, self.manifest.db_edition, db_type=self.manifest.db_type)
        initial_package = self.manifest.package

        # Resolve the package path using env.get_package
        initial_package_path = self.env.get_package(initial_package) if initial_package else None

        initial_db = create_db(
            docker_manager=self.docker_manager,
            db_installer=self.db_installer,
            pgdg_installer=self.env.pgdg_installer,
            logs_dir=self.env.logs_dir,
            db_path=self.env.new_db,
            version=initial_version,
            nexus_env=self.nexus_env,
            package_path=initial_package_path,
            db_type=self.manifest.db_type
        )
        # Create an old database as an empty structure
        old_db = Database(
            version=None,
            bin_path=None,
            data_path=self.env.old_db,
            logs_dir=self.env.logs_dir,
            docker_manager=self.docker_manager,
        )

        # Clean up data directories
        for db in [initial_db, old_db]:
            self.clean_db_directory(db.data_path)

        # Initialize the initial database
        initdb(initial_db)

        self.state = {
            'old_db': old_db,
            'new_db': initial_db,
            'step': None,
        }

    def clean_db_directory(self, db_path: str):
        self.docker_manager.shell('rm', '-rf', db_path)
        self.docker_manager.shell('mkdir', '-p', db_path)
        self.docker_manager.shell('chmod', '0700', db_path)
        self.docker_manager.shell('chown', 'postgres:postgres', db_path)

    def prepare_step(self, step: MigrationStep):
        # Move new database files to the old database directory
        old_data = self.state['old_db'].data_path
        new_data = self.state['new_db'].data_path
        self.docker_manager.shell('rm', '-rf', old_data)
        self.docker_manager.shell('mv', new_data, old_data)

        # Update data paths
        self.state['new_db'].data_path = old_data
        self.state['old_db'], self.state['new_db'] = self.state['new_db'], self.state['old_db']

        # Create a new database
        new_version = DbVersion.create(step.db_version, step.db_edition, self.manifest.db_type)
        new_package = step.package

        # Resolve the package path
        new_package_path = self.env.get_package(new_package) if new_package else None

        new_db = create_db(
            docker_manager=self.docker_manager,
            db_installer=self.db_installer,
            pgdg_installer=self.env.pgdg_installer,
            logs_dir=self.env.logs_dir,
            db_path=self.env.new_db,
            version=new_version,
            nexus_env=self.nexus_env,
            db_type=self.manifest.db_type,
            package_path=new_package_path
        )
        self.state['new_db'] = new_db
        self.state['step'] = step

    def run_step(self):
        # Execute the current migration step based on its type
        step_type = self.state['step'].type
        if step_type == MigrationStrategy.MINOR:
            self.run_minor()
        else:
            self.initialize_db_cluster()
            self.run_pre_step()

            if step_type == MigrationStrategy.PG_UPGRADE:
                self.run_pg_upgrade()
            elif step_type == MigrationStrategy.PG_DUMPALL:
                self.run_pg_dumpall()
            else:
                raise NotImplementedError(f"Migration strategy {step_type} not implemented")
            self.run_post_step()
        self.run_verifier()

    def initialize_db_cluster(self):
        # Initialize the new database cluster
        new_db = self.state['new_db']
        self.docker_manager.shell('mkdir', '-p', new_db.data_path)
        self.docker_manager.shell('chown', 'postgres:postgres', new_db.data_path)
        logger.info('Initializing PostgreSQL (%s) cluster', new_db.version)
        initdb(new_db)

    def run_minor(self):
        self.run_pre_step()
        # Handle minor migration strategy
        old_db = self.state['old_db']
        new_db = self.state['new_db']

        old_major = old_db.version.major
        new_major = new_db.version.major

        if old_major != new_major:
            raise ValueError(
                f"Minor upgrade невозможно: несовпадение major версии. "
                f"Текущая: {old_major}, целевая: {new_major}."
            )

        old_data = old_db.data_path
        new_data = new_db.data_path

        self.docker_manager.shell('rm', '-rf', new_data)
        self.docker_manager.shell('mv', old_data, new_data)
        self.docker_manager.shell('mkdir', '-p', old_data)
        self.docker_manager.shell('chmod', '0700', old_data)
        self.docker_manager.shell('chown', 'postgres:postgres', old_data)

        self.run_db()
        self.stop_db()
        self.run_post_step()

    def run_pg_upgrade(self):
        # Perform a pg_upgrade migration step
        new_db = self.state['new_db']
        old_db = self.state['old_db']
        pg_upgrade(new_db, old_db)

    def run_pg_dumpall(self):
        # Perform a pg_dumpall migration step
        new_db = self.state['new_db']
        old_db = self.state['old_db']
        new_version = new_db.version
        old_version = old_db.version

        logger.info('Starting PostgreSQL (%s) cluster', old_version)
        run_db(old_db)

        dump_file = self.env.get_temp_filename(f'dump_{old_version}.sql')
        logger.info('Running pg_dumpall (%s)', new_version)
        pg_dumpall(new_db, dump_file)

        logger.info('Stopping PostgreSQL (%s) cluster', old_version)
        stop_db(old_db)

        logger.info('Copying configuration files from %s to %s', old_version, new_version)
        self.copy_configuration_files(old_db.data_path, new_db.data_path)

        logger.info('Starting PostgreSQL (%s) cluster', new_version)
        run_db(new_db)

        logger.info('Running psql (%s) for loading DB dump', new_version)
        run_sql_script(new_db, dump_file)

        logger.info('Stopping PostgreSQL (%s) cluster', new_version)
        stop_db(new_db)

    def copy_configuration_files(self, old_data_path: str, new_data_path: str):
        # Copy configuration files from the old database to the new one
        config_files = ['postgresql.conf', 'postgresql.auto.conf', 'pg_hba.conf']
        for filename in config_files:
            old_file = os.path.join(old_data_path, filename)
            new_file = os.path.join(new_data_path, filename)
            try:
                self.docker_manager.shell('cp', old_file, new_file)
            except Exception as e:
                logger.error('Failed to copy %s to new db: %s', filename, e)
                raise RuntimeError(f'Failed to copy {filename} to new db') from e

    def run_db(self):
        # Start the new database
        new_db = self.state['new_db']
        logger.info('Starting PostgreSQL (%s)', new_db.version)
        run_db(new_db)

    def stop_db(self):
        # Stop the new database
        new_db = self.state['new_db']
        stop_db(new_db)

    def run_scripts(self, scripts: ScriptList, stage: str):
        # Run scripts for the specified stage
        if not scripts:
            return

        script_list = self.extract_plain_script_list(scripts)
        if not script_list:
            return

        logger.info('Running stage: %s', stage)
        self.run_db()
        for script in script_list:
            if script.endswith('.sql'):
                self.run_psql_script(script)
            else:
                self.run_shell_script(script)
        self.stop_db()

    def run_pre_step(self):
        # Run pre-step scripts
        step = self.state['step']
        if step.type == MigrationStrategy.MINOR:
            # Run initial_pre_scripts if minor
            pre_scripts = self.manifest.initial_pre_scripts or self.manifest.pre_scripts
        else:
            # Run pre_scripts for other step
            pre_scripts = step.pre_scripts or self.manifest.pre_scripts

        self.run_scripts(pre_scripts, 'pre')

    def run_post_step(self):
        # Run post-step scripts
        step = self.state['step']
        if step.type == MigrationStrategy.MINOR:
            # Run initial_post_scripts if minor
            post_scripts = self.manifest.initial_post_scripts or self.manifest.post_scripts
        else:
            # Run post_scripts for other step
            post_scripts = step.post_scripts or self.manifest.post_scripts

        self.run_scripts(post_scripts, 'post')

    def run_post_step(self):
        # Run post-step scripts
        step_scripts = self.state['step'].post_scripts or self.manifest.post_scripts
        self.run_scripts(step_scripts, 'post')

    def run_verifier(self):
        # Run verifier scripts
        step_scripts = self.state['step'].verifiers or self.manifest.verifiers
        self.run_scripts(step_scripts, 'verifier')

    def run_psql_script(self, script: str):
        # Execute a SQL script using psql
        script_path = self.env.get_script(script)
        new_db = self.state['new_db']
        logger.info('Running SQL script %s (%s)', script, new_db.version)
        run_sql_script(new_db, script_path)

    def run_shell_script(self, script: str):
        # Execute a shell script
        script_path = self.env.get_script(script)
        new_db = self.state['new_db']
        logger.info('Running shell script %s (%s)', script, new_db.version)
        run_shell_script(new_db, script_path)

    def extract_plain_script_list(self, scripts: ScriptList) -> Optional[List[str]]:
        # Convert a script or list of scripts into a uniform list
        if not scripts:
            return None
        if isinstance(scripts, str):
            return [scripts]
        elif isinstance(scripts, list):
            return scripts
        else:
            logger.error('Invalid script list type: %s', type(scripts))
            return None


def run_migration(manifest: MigrationManifest, docker_manager: DockerContainerManager, env: Environment):
    runner = MigrationRunner(manifest, docker_manager, env)
    runner.run_migration()
