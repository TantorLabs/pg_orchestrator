import os
import pytest
from unittest.mock import patch, MagicMock
from src.manifest import read_migration_manifest
from upgrade.upgrade import check_scripts_exist, check_packages_exist, prepare_environment, run_upgrade
from src.manifest import MigrationManifest, MigrationStep, MigrationStrategy, DockerConfig
from upgrade.database import run_pg_binary, pg_upgrade, DbVersion, Database, NexusEnv, run_sql_script
from upgrade.migration import MigrationRunner, Environment

@pytest.fixture
def manifest():
    conf_path = os.path.join(os.path.dirname(__file__), 'upgrade_test', 'conf.yaml')
    with open(conf_path, 'r') as f:
        return read_migration_manifest(f)

@patch('upgrade.upgrade.DockerContainerManager')
@patch('upgrade.upgrade.run_migration')
def test_upgrade_scenario(mock_run_migration, mock_docker, manifest, tmp_path):
    # Mock DockerContainerManager to avoid running real containers
    mock_manager_instance = MagicMock()
    mock_docker.return_value = mock_manager_instance

    # Run `run_upgrade` with the provided manifest
    scenario_path = tmp_path / "scenario"
    scenario_path.mkdir()

    # Create fake directories for scripts and packages
    (scenario_path / "scripts").mkdir()
    (scenario_path / "packages").mkdir()

    # Check that `run_migration` was called
    run_upgrade(manifest, str(scenario_path))
    mock_run_migration.assert_called_once()

    # Verify that DockerContainerManager methods were invoked
    mock_manager_instance.start_container.assert_called_once()

@pytest.fixture
def basic_manifest():
    return MigrationManifest(
        kind="upgrade",
        db_type="ttdb",
        db_version="14.11.0",
        db_edition="se",
        docker=DockerConfig(
            image="tt_build_ubuntu:22.04"
        ),
        steps=[],
    )

def test_check_scripts_exist(basic_manifest, tmp_path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    # Create a required script
    script_file = scripts_dir / "test.sql"
    script_file.touch()

    basic_manifest.pre_scripts = "test.sql"
    # Should pass without errors
    check_scripts_exist(str(scripts_dir), basic_manifest)

    # Should raise an error if the script name is changed
    basic_manifest.pre_scripts = "not_exists.sql"
    with pytest.raises(FileNotFoundError):
        check_scripts_exist(str(scripts_dir), basic_manifest)

def test_check_packages_exist(basic_manifest, tmp_path):
    packages_dir = tmp_path / "packages"
    packages_dir.mkdir()
    pkg = packages_dir / "pkg.deb"
    pkg.touch()

    basic_manifest.package = "pkg.deb"
    # Should pass without errors
    check_packages_exist(str(packages_dir), basic_manifest)

    # Should raise an error if the package name is changed
    basic_manifest.package = "nopkg.deb"
    with pytest.raises(FileNotFoundError):
        check_packages_exist(str(packages_dir), basic_manifest)

def test_prepare_environment(basic_manifest, tmp_path):
    scenario_path = tmp_path
    (scenario_path / "scripts").mkdir()
    (scenario_path / "packages").mkdir()

    env = prepare_environment(str(scenario_path), basic_manifest)
    assert os.path.exists(env.logs_dir)

    # If there are scripts in the manifest, then scripts_dir must be set and exist,
    # otherwise it must be None.
    def has_scripts(manifest):
        scripts = []
        for field in (manifest.pre_scripts, manifest.post_scripts, manifest.verifiers,
                      manifest.initial_pre_scripts, manifest.initial_post_scripts):
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

    if has_scripts(basic_manifest):
        assert env.scripts_dir is not None and os.path.exists(env.scripts_dir)
    else:
        assert env.scripts_dir is None

    # The same for packages dir:
    def has_packages(manifest):
        if manifest.package:
            return True
        for step in manifest.steps:
            if step.package:
                return True
        return False

    if has_packages(basic_manifest):
        assert env.packages_dir is not None and os.path.exists(env.packages_dir)
    else:
        assert env.packages_dir is None

    assert env.db_installer.endswith("db_installer.sh")

def test_run_upgrade_success(basic_manifest, tmp_path):
    # Verify that `run_upgrade` calls required functions without errors
    (tmp_path / "scripts").mkdir()
    (tmp_path / "packages").mkdir()

    env = prepare_environment(str(tmp_path), basic_manifest)
    with patch('upgrade.upgrade.run_migration') as mock_run_migration, \
         patch('upgrade.upgrade.create_docker_manager') as mock_create_manager:
        mock_context_manager = MagicMock()
        mock_create_manager.return_value = mock_context_manager
        mock_context_manager.__enter__.return_value = MagicMock()
        run_upgrade(basic_manifest, str(tmp_path))
        mock_run_migration.assert_called_once()

@pytest.fixture
def mock_db():
    version = DbVersion(version="15.6.0", edition="se", major="15", db_type="ttdb")
    mock_manager = MagicMock()
    db = Database(
        version=version,
        bin_path="/opt/tantor/db/15/bin",
        data_path="/tmp/new_data",
        logs_dir="/tmp/logs",
        docker_manager=mock_manager
    )
    return db

def test_pg_upgrade_error_logs(mock_db):
    # Simulate success for copying postgresql.conf and failure for pg_upgrade
    def side_effect(*args, **kwargs):
        if 'pg_upgrade' in args[-1]:
            raise Exception("pg_upgrade failed")
        return (0, "OK")

    mock_db.docker_manager.shell.side_effect = side_effect

    with pytest.raises(Exception, match="pg_upgrade failed"):
        pg_upgrade(mock_db, mock_db)

    # Check if mkdir and cp commands were called for error logs
    mock_db.docker_manager.shell.assert_any_call('mkdir', '-p', '/tmp/logs/additionally_errors_logs')
    calls = [call.args for call in mock_db.docker_manager.shell.call_args_list]
    assert any('pg_upgrade_output.d' in str(c) for ca in calls for c in ca)

def test_run_pg_binary_error_handling(mock_db, tmp_path):
    # Test that logs are copied in case of pg_upgrade failure
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    mock_db.docker_manager.shell.side_effect = Exception("pg_upgrade error")

    with pytest.raises(Exception):
        run_pg_binary(mock_db, 'pg_upgrade', '--arg')

    # Check if error logs were created and copied
    mock_db.docker_manager.shell.assert_any_call('mkdir', '-p', os.path.join(mock_db.logs_dir, 'additionally_errors_logs'))

@pytest.fixture
def mock_db_2():
    version = DbVersion(version="16.6.0", edition="se", major="16", db_type="ttdb")
    mock_manager = MagicMock()
    db = Database(
        version=version,
        bin_path="/opt/tantor/db/16/bin",
        data_path="/tmp/new_data",
        logs_dir="/tmp/logs",
        docker_manager=mock_manager
    )
    return db

def test_run_sql_script_error_parsing(mock_db_2, tmp_path):
    logfilename = f'psql_{mock_db_2.version}.log'
    logfile = os.path.join(mock_db_2.logs_dir, logfilename)

    os.makedirs(mock_db_2.logs_dir, exist_ok=True)
    with open(logfile, 'w') as f:
        f.write("psql:update_extensions.sql:6: ERROR:  some error happened\n")

    # Mock successful psql execution but with an error logged
    mock_db_2.docker_manager.shell.return_value = (0, "psql executed")

    with pytest.raises(RuntimeError, match="Error found during execution"):
        run_sql_script(mock_db_2, '/fake/script.sql')

@pytest.fixture
def base_env(tmp_path):
    return Environment(
        tmp_dir=str(tmp_path),
        new_db=str(tmp_path / "new_data"),
        old_db=str(tmp_path / "old_data"),
        logs_dir=str(tmp_path / "logs"),
        scripts_dir=str(tmp_path / "scripts"),
        packages_dir=str(tmp_path / "packages"),
        db_installer="/fake/db_installer.sh",
        pgdg_installer="/fake/pgdg_installer.sh"
    )

@patch('upgrade.database.run_pg_binary')
@patch('upgrade.migration.run_db')
@patch('upgrade.migration.stop_db')
def test_pg_dumpall_step(mock_stop_db, mock_run_db, mock_run_pg_binary, basic_manifest, base_env):
    # Add a pg_dumpall step
    step = MigrationStep(
        type=MigrationStrategy.PG_DUMPALL,
        db_version="16.6.0",
        db_edition="se"
    )
    basic_manifest.steps = [step]

    docker_manager = MagicMock()
    nexus_env = MagicMock(spec=NexusEnv)

    runner = MigrationRunner(basic_manifest, docker_manager, base_env)

    with patch('upgrade.migration.create_db') as mock_create_db, \
         patch('upgrade.migration.initdb'):
        mock_db_old = Database(DbVersion.create("14.11.0", "se", "ttdb"), "/path/bin", "/path/old", "/path/logs", docker_manager)
        mock_db_new = Database(DbVersion.create("14.11.0", "se", "ttdb"), "/path/bin", "/path/new", "/path/logs", docker_manager)
        mock_create_db.side_effect = [mock_db_new]
        runner.create_initial_state()

    runner.run_migration()

    calls = [c.args for c in mock_run_pg_binary.call_args_list]
    # Verify that the second argument is 'pg_dumpall'
    assert any(ca[1] == 'pg_dumpall' for ca in calls)

@pytest.fixture
def basic_2_manifest():
    return MigrationManifest(
        kind="upgrade",
        db_type="ttdb",
        db_version="15.8.0",
        db_edition="se",
        docker=DockerConfig(
            image="tt_build_ubuntu:22.04"
        ),
        steps=[],
    )

@patch('upgrade.database.run_pg_binary')
@patch('upgrade.migration.run_db')
@patch('upgrade.migration.stop_db')
def test_minor_step(mock_stop_db, mock_run_db, mock_run_pg_binary, basic_2_manifest, base_env):
    # Add a minor upgrade step
    step = MigrationStep(
        type=MigrationStrategy.MINOR,
        db_version="15.10.0",
        db_edition="se",
        args={'pg_upgrade': '--link'}
    )
    basic_2_manifest.steps = [step]

    docker_manager = MagicMock()
    nexus_env = MagicMock(spec=NexusEnv)
    runner = MigrationRunner(basic_2_manifest, docker_manager, base_env)

    with patch('upgrade.migration.create_db') as mock_create_db, \
         patch('upgrade.migration.initdb'):
        mock_db_old = Database(DbVersion.create("14.11.0","se","ttdb"), "/path/bin", "/path/old","/path/logs", docker_manager)
        mock_db_new = Database(DbVersion.create("14.11.0","se","ttdb"), "/path/bin", "/path/new","/path/logs", docker_manager)
        mock_create_db.side_effect = [mock_db_new]
        runner.create_initial_state()

    runner.run_migration()

    # Verify that `run_db` and `stop_db` were called
    mock_run_db.assert_called()
    mock_stop_db.assert_called()

    calls = [c.args for c in mock_run_pg_binary.call_args_list]
    # Ensure `pg_upgrade` or `pg_dumpall` were not called
    assert not any('pg_upgrade' in ca for ca in calls for ca in ca if isinstance(ca, str))
    assert not any('pg_dumpall' in ca for ca in calls for ca in ca if isinstance(ca, str))
