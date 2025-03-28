from contextlib import contextmanager
from dataclasses import dataclass
import itertools
import os

from manager.dockerManager import DockerContainerManager
from src.logger import logger, TIMESTAMP
from .migration import run_migration, Environment
from src.manifest import MigrationManifest


@contextmanager
def create_docker_manager(env: Environment, manifest: MigrationManifest):
    logger.debug('Creating container')
    manager = DockerContainerManager(
        image_name=manifest.docker.image,
        container_name=manifest.docker.container_name or f'pg_orchestrator_upgrade',
        registry_url=f"{manifest.docker.registry}",
        host_port=manifest.docker.host_port,
        use_host_network=True,
        volumes={
            path: {'bind': path} for path in (env.logs_dir, env.scripts_dir, env.packages_dir, env.pgdg_installer) if
            path is not None and os.path.exists(path)
        },

    )

    try:
        logger.debug('Starting Docker container')
        manager.start_container()
        yield manager
    except Exception as e:
        logger.exception('Failed to start Docker container')
        raise
    finally:
        logger.debug('Stopping Docker container')
        # manager.stop_container()

def check_scripts_exist(scripts_path: str, manifest: MigrationManifest) -> None:
    """
    Check exists all script files, which defined in MigrationManifest
    such as pre_scripts, post_scripts and verifiers
    """
    def iter_script_list(scripts):
        if not scripts:
            return []
        if isinstance(scripts, str):
            return [scripts]
        if isinstance(scripts, list):
            return scripts
        raise TypeError(f'Expected str or list, got {type(scripts).__name__}')

    def iter_scripts():
        for scripts in (manifest.pre_scripts, manifest.post_scripts, manifest.verifiers):
            yield from iter_script_list(scripts)
        for step in manifest.steps:
            for scripts in (step.pre_scripts, step.post_scripts, step.verifiers):
                yield from iter_script_list(scripts)

    missing_scripts = []
    for script in iter_scripts():
        if script:
            script_path = os.path.join(scripts_path, script)
            if not os.path.exists(script_path):
                missing_scripts.append(script_path)

    if missing_scripts:
        raise FileNotFoundError(f'Script files not found: {", ".join(missing_scripts)}')

def check_packages_exist(packages_dir: str, manifest: MigrationManifest):
    """
    Check packages for each step
    """
    package_files = []

    if manifest.package:
        package_files.append(manifest.package)

    for step in manifest.steps:
        if step.package:
            package_files.append(step.package)

    for package in package_files:
        path = os.path.join(packages_dir, package)
        if not os.path.isfile(path):
            raise FileNotFoundError(f'Package file not found: {path}')


def prepare_environment(scenario_path: str, manifest: MigrationManifest):
    tmp_dir = '/tmp'
    new_db = os.path.abspath(os.path.join(tmp_dir, 'new_data'))
    old_db = os.path.abspath(os.path.join(tmp_dir, 'old_data'))

    # Needs scripts dir or not
    def has_scripts(manifest: MigrationManifest) -> bool:
        scripts = []
        for field in (manifest.pre_scripts, manifest.post_scripts, manifest.verifiers,
                      manifest.initial_pre_scripts, manifest.initial_post_scripts,
                      manifest.initial_setup_script):
            if field:
                if isinstance(field, list):
                    scripts.extend(field)
                else:
                    scripts.append(field)
        for step in manifest.steps:
            for field in (step.pre_scripts, step.post_scripts, step.verifiers):
                if field:
                    if isinstance(field, list):
                        scripts.extend(field)
                    else:
                        scripts.append(field)
        return len(scripts) > 0

    if has_scripts(manifest):
        scripts_dir = os.path.abspath(os.path.join(scenario_path, 'scripts'))
        check_scripts_exist(scripts_dir, manifest)
    else:
        scripts_dir = None

    # Needs packages dir or not
    def has_packages(manifest: MigrationManifest) -> bool:
        if manifest.package:
            return True
        for step in manifest.steps:
            if step.package:
                return True
        return False

    if has_packages(manifest):
        packages_dir = os.path.abspath(os.path.join(scenario_path, 'packages'))
        check_packages_exist(packages_dir, manifest)
    else:
        packages_dir = None

    logs_dir = os.path.abspath(os.path.join('logs', f'upgrade_dbms_{TIMESTAMP}'))
    os.makedirs(logs_dir, exist_ok=True)
    logger.debug('Logs directory is set to %s', logs_dir)

    # For ttdb installer
    db_installer = os.path.abspath('db_installer.sh')
    # For pgdg installer
    pgdg_installer = os.path.abspath('src/pgdg_installer.sh')

    return Environment(
        tmp_dir=tmp_dir,
        new_db=new_db,
        old_db=old_db,
        logs_dir=logs_dir,
        scripts_dir=scripts_dir,
        packages_dir=packages_dir,
        db_installer=db_installer,
        pgdg_installer=pgdg_installer
    )


def prepare_container_env(env: Environment, manager: DockerContainerManager,  db_type: str):
    for data in [env.new_db, env.old_db]:
        if os.path.exists(data):
            manager.shell('rm', '-rf', data)

    if db_type == 'ttdb':
        logger.debug('Downloading db_installer.sh')
        manager.shell('apt-get', 'update')
        manager.shell('apt-get', 'install', '-y', 'wget')
        manager.shell('wget', 'https://public.tantorlabs.ru/db_installer.sh', '-O', env.db_installer)
        manager.shell('chmod', '+x', env.db_installer)

    if env.scripts_dir and os.path.exists(env.scripts_dir):
        manager.shell('chmod', '-R', '+x', env.scripts_dir)
    if env.packages_dir and os.path.exists(env.packages_dir):
        manager.shell('chmod', '-R', '+r', env.packages_dir)

def run_upgrade(manifest: MigrationManifest, scenario_path: str):
    env = prepare_environment(scenario_path, manifest)
    with create_docker_manager(env, manifest) as manager:
        prepare_container_env(env, manager, manifest.db_type)
        run_migration(manifest, manager, env)

        logger.info('Migration completed successfully')
