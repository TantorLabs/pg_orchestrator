import asyncpg
import asyncio
import time

from src.logger import *
from manager.dockerManager import *
from src.manifest import PerformanceManifest


def prepare_database(test, manifest, docker_manager):
    """
    Prepares the database inside the container according to the test parameters.

    :param test: Instance of DBParam with database parameters.
    :param manifest: Instance of PerformanceManifest with configuration details.
    :param docker_manager: DockerContainerManager for managing the container.
    """
    def get_data_directory() -> str:
        """
        Returns the data directory path based on the db_type.
        """
        if test.db_type == "ttdb":
            return f"/var/lib/postgresql/tantor-{test.db_edition}-{test.db_major_version}/data"
        elif test.db_type == "pgdg":
            return f"/var/lib/postgresql/{test.pgdg_maintanance_version}/data"
        else:
            raise ValueError(f"Unsupported db_type: {test.db_type}")

    def get_pg_ctl_command() -> str:
        """
        Returns the pg_ctl command for starting PostgreSQL.
        """
        data_dir = get_data_directory()
        if test.db_type == "ttdb":
            return f'su - postgres -c "/opt/tantor/db/{test.db_major_version}/bin/pg_ctl -D {data_dir} -l logfile start"'
        elif test.db_type == "pgdg":
            return f'su - postgres -c "/usr/local/pgsql/bin/pg_ctl -D {data_dir} -l logfile start"'

    def get_psql_version_command() -> str:
        """
        Returns the psql command for checking PostgreSQL version.
        """
        if test.db_type == "ttdb":
            return (f'su - postgres -c "/opt/tantor/db/{test.db_major_version}/bin/psql -c '
                    f'\\"select tantor_version();\\""')
        elif test.db_type == "pgdg":
            return (f'su - postgres -c "/usr/local/pgsql/bin/psql -c '
                    f'\\"select version();\\""')


    # Installation block (commands specific to the database type)
    commands_install = []
    if test.db_type == "ttdb":
        logger.info("Detected db_type as 'ttdb'. Preparing commands for ttdb installation.")
        commands_install.extend([
            ('apt-get update', "Updating repos of ubuntu"),
            ('apt-get install wget locales-all -y', "Installing wget and locales-all"),
            ('wget https://public.tantorlabs.ru/db_installer.sh', "Downloading db_installer.sh script"),
            ('chmod +x db_installer.sh', "Setting execute permissions for db_installer.sh"),
            (f'./db_installer.sh --do-initdb --major-version={test.db_major_version} '
             f'--maintenance-version={test.db_version} --edition={test.db_edition}',
             f"Running db_installer.sh with parameters version: {test.db_version}, edition: {test.db_edition}")
        ])
    elif test.db_type == "pgdg":
        logger.info("Detected db_type as 'pgdg'. Preparing commands for pgdg installation.")
        commands_install.append(('chmod +x pgdg_installer.sh', "Setting execute permissions for pgdg_installer.sh"))
        commands_install.append((f'./pgdg_installer.sh --maintenance-version={test.pgdg_maintanance_version} --with-initdb',
                                 f"Running pgdg_installer.sh with parameter version: {test.pgdg_maintanance_version}"))
    else:
        logger.warning(f"Unknown db_type: {test.db_type}. No commands will be executed.")
        commands_install = []

    # After installation, start the DBMS with minimal configuration
    if test.db_type in ("ttdb", "pgdg"):
        data_dir = get_data_directory()
        # Minimal configuration: pg_hba.conf and DBMS startup
        commands_install.append((
            f'su - postgres -c "echo \'host all all 0.0.0.0/0 trust\' >> {data_dir}/pg_hba.conf"',
            "Configuring minimal pg_hba.conf"
        ))
        commands_install.append((get_pg_ctl_command(), "Starting PostgreSQL with pg_ctl"))

    # Execute installation block
    for cmd, desc in commands_install:
        logger.info(f"Executing command: {cmd} - {desc}")
        exit_code = docker_manager.exec_command(cmd, log_to_file=True)
        if exit_code != 0:
            logger.error(f"Command failed with exit code {exit_code}: {cmd}")
            raise RuntimeError(f"Command failed with exit code {exit_code}: {cmd}")

    # Before executing the initial_script, the DBMS is already running
    if manifest.initial_script:
        # Check that initial_script exists
        initial_script_local_path = os.path.join(os.getcwd(), manifest.initial_script)
        if os.path.isfile(initial_script_local_path):
            if manifest.initial_script.endswith('.sh'):
                initial_cmd = f"bash /scenario/{manifest.initial_script}"
            elif manifest.initial_script.endswith('.py'):
                initial_cmd = f"python /scenario/{manifest.initial_script}"
            else:
                initial_cmd = f"/scenario/{manifest.initial_script}"
            logger.info(f"Executing initial script: {initial_cmd}")
            exit_code = docker_manager.exec_command(initial_cmd, log_to_file=True)
            if exit_code != 0:
                logger.error(f"Initial script {manifest.initial_script} failed with exit code {exit_code}")
                raise RuntimeError(f"Initial script {manifest.initial_script} failed with exit code {exit_code}")
        else:
            logger.error(f"Initial script file does not exist: {initial_script_local_path}")
            raise RuntimeError(f"Initial script file does not exist: {initial_script_local_path}")

    # If a configuration file is specified, execute the PostgreSQL configuration block
    if manifest.configuration:
        data_dir = get_data_directory()
        commands_config = [
            (f'su - postgres -c "cat /scenario/{manifest.configuration} >> {data_dir}/postgresql.conf"',
             f"Appending configuration {manifest.configuration} to postgresql.conf"),
            (f'su - postgres -c "sed -i \\"s/^#listen_addresses.*/listen_addresses = \'*\'/\\" {data_dir}/postgresql.conf"',
             "Updating listen_addresses in postgresql.conf to listen on all addresses"),
            (f'su - postgres -c "echo \'host all all 0.0.0.0/0 trust\' >> {data_dir}/pg_hba.conf"',
             "Configuring pg_hba.conf"),
            (get_pg_ctl_command(), "Starting PostgreSQL with pg_ctl"),
            (get_psql_version_command(), "Running command to check PostgreSQL version")
        ]
        for cmd, desc in commands_config:
            logger.info(f"Executing command: {cmd} - {desc}")
            exit_code = docker_manager.exec_command(cmd, log_to_file=True)
            if exit_code != 0:
                logger.error(f"Command failed with exit code {exit_code}: {cmd}")
                raise RuntimeError(f"Command failed with exit code {exit_code}: {cmd}")

async def run_perf(manifest: PerformanceManifest, scenario_path):
    # Path to the 'cases' directory within the scenario
    cases_dir = os.path.join(scenario_path, 'cases')

    # Check that the 'cases' directory exists
    if not os.path.isdir(cases_dir):
        raise ValueError(f"'cases' directory does not exist in scenario path: {scenario_path}")

    manifest.db_initial_script = os.path.join(scenario_path, manifest.db_initial_script)
    print(manifest.db_initial_script)

    # List with results, here will be results of each performed cases
    test_results = []

    # Process each test from the manifest
    for test in manifest.db_params:
        logger.info(f"Starting test for version: {test.db_version}, edition: {test.db_edition}")

        test_result = {
            'test_version': test.db_version,
            'test_edition': test.db_edition,
            'cases': []
        }
        if test.db_type == 'ttdb':

            # Getting Nexus credentials from environment variables
            NEXUS_USER = os.environ.get('NEXUS_USER')
            NEXUS_USER_PASSWORD = os.environ.get('NEXUS_USER_PASSWORD')
            NEXUS_URL = os.environ.get('NEXUS_URL')

            # Passing environment variables to the container
            environment_vars = {
                "NEXUS_USER": NEXUS_USER,
                "NEXUS_USER_PASSWORD": NEXUS_USER_PASSWORD,
                "NEXUS_URL": NEXUS_URL
            }

            if not NEXUS_USER or not NEXUS_USER_PASSWORD or not NEXUS_URL:
                raise ValueError("Environment variables NEXUS_USER, NEXUS_USER_PASSWORD, and NEXUS_URL must be set.")

            if test.db_edition is None:
                raise ValueError(
                    f"If you using {test.db_type}, you  must be set db_edition in {scenario_path}/conf.yaml.")

            docker_manager = DockerContainerManager(
                image_name=f"{manifest.docker.image}",
                container_name=f"pg_orchestrator_{manifest.kind}",
                environment_vars=environment_vars,
                registry_url=f"{manifest.docker.registry}",
                host_port=test.db_port,
                container_port=5432,
                use_host_network=True,
                volumes={
                    os.path.abspath(f'{scenario_path}'): {'bind': '/scenario', 'mode': 'rw'}
                    # Mounting the configurations directory
                }
            )
        elif test.db_type == 'pgdg':
            docker_manager = DockerContainerManager(
                image_name=f"{manifest.docker.image}",
                container_name=f"pg_orchestrator_{manifest.kind}",
                registry_url=f"{manifest.docker.registry}",
                host_port=test.db_port,
                container_port=5432,
                use_host_network=True,
                volumes={
                    os.path.abspath(f'{scenario_path}'): {'bind': '/scenario', 'mode': 'rw'},
                    os.path.abspath('src/pgdg_installer.sh'): {'bind': '/pgdg_installer.sh', 'mode': 'rw'}
                    # Mounting the configurations directory
                }
            )
        else:
            print(f'This db_type not allowed: {test.db_type}!')

        logger.info(f"Starting container {docker_manager.container_name} with {docker_manager.image_name}")

        # Start the container
        docker_manager.start_container()

        prepare_database(test, manifest, docker_manager)

        logger.info(
            f"End of installing release: {test.db_type} for version: {test.db_version} container: {docker_manager.container}")

        # Waiting for database is ready
        logger.info("Waiting for database to be ready...")
        await wait_for_db_ready(host='localhost', port=test.db_port, user='postgres')

        # Set path to fill_db.sh
        # manifest.db_initial_script = os.path.join(scenario_path, manifest.db_initial_script)

        # Perf fill_db.sh from su - postgres
        logger.info("Executing db_initial_script as postgres to filling the database")
        fill_db_script_container_path = f"/scenario/{os.path.basename(manifest.db_initial_script)}"
        command = f"su - postgres -c 'bash {fill_db_script_container_path}'"
        result = docker_manager.exec_command(command)
        logger.info(f"Executed {manifest.db_initial_script} as postgres, result: {result}")

        # Listing files in case_*
        for case in manifest.cases:
            case_name = case.name
            logger.info(f"Processing {case_name} for test version {test.db_version}")

            case_result = {
                'case_name': case_name,
                'explain_results': [],
                'timing_results': [],
                'pre_hook_result': None,
                'post_hook_result': None
            }

            case_dir = os.path.join(scenario_path, 'cases', case_name)

            if not os.path.isdir(case_dir):
                logger.error(f"Case directory does not exist: {case_dir}")
                continue

            if case.pre_hook:
                pre_hook_path = os.path.join(case_dir, case.pre_hook)
                if os.path.isfile(pre_hook_path):
                    logger.info(f"Executing pre_hook for {case_name}")
                    container_pre_hook_path = f"/scenario/cases/{case_name}/{case.pre_hook}"
                    if case.pre_hook.endswith('.sh'):
                        command = f"bash {container_pre_hook_path}"
                    elif case.pre_hook.endswith('.py'):
                        command = f"python {container_pre_hook_path}"
                    else:
                        logger.warning(f"Unknown pre_hook file type for {case_name}: {case.pre_hook}")
                        continue
                    docker_manager.exec_command(command)
                    logger.info(f"Executed pre_hook for {case_name}")
                else:
                    logger.error(f"pre_hook file does not exist for {case_name}: {pre_hook_path}")

            conn_params = {
                'host': 'localhost',
                'port': test.db_port,
                'user': 'postgres'
            }

            # Check which files to execute
            if case.explain_queries:
                for explain_query in case.explain_queries:
                    explain_query_path = os.path.join(case_dir, explain_query.query)
                    if not os.path.isfile(explain_query_path):
                        logger.error(f"Explain query file does not exist for {case_name}: {explain_query_path}")
                        continue

                    with open(explain_query_path, 'r') as f:
                        explain_query_sql = f.read()

                    # EXPLAIN (VERBOSE, COSTS OFF)
                    explain_plan = await execute_explain_query(explain_query_sql, conn_params)
                    # Saving actual execution plan
                    actual_explain_plan = explain_plan

                    # Check actual plan with expected_*
                    match_found = False
                    matched_expected_file = None
                    expected_plans = []
                    for expected_file_name in explain_query.expected:
                        expected_file_path = os.path.join(case_dir, expected_file_name)
                        if not os.path.isfile(expected_file_path):
                            logger.error(f"Expected explain plan file does not exist: {expected_file_path}")
                            continue
                        with open(expected_file_path, 'r') as f:
                            expected_plan = f.read()
                            expected_plans.append((expected_file_name, expected_plan))

                        if actual_explain_plan.strip() == expected_plan.strip():
                            logger.info(f"Explain plan matches expected plan in {expected_file_name}")
                            match_found = True
                            matched_expected_file = expected_file_name
                            break
                    if not match_found:
                        logger.warning(f"No matching explain plan found for {case_name}")
                        logger.info(f"Actual explain plan:\n{actual_explain_plan}")
                        for expected_file_name, expected_plan in expected_plans:
                            logger.info(f"Expected explain plan from {expected_file_name}:\n{expected_plan}")

                    # Saved results to case_result
                    case_result['explain_results'].append({
                        'query': explain_query.query,
                        'result': 'match' if match_found else 'no match',
                        'actual_plan': actual_explain_plan,
                        'expected_plans': expected_plans,
                        'matched_expected_file': matched_expected_file
                    })

            if case.timing_queries:
                for timing_query in case.timing_queries:
                    timing_query_path = os.path.join(case_dir, timing_query.query)
                    if not os.path.isfile(timing_query_path):
                        logger.error(f"Timing query file does not exist for {case_name}: {timing_query_path}")
                        continue

                    with open(timing_query_path, 'r') as f:
                        timing_query_sql = f.read()

                    # Preforming query for checking timing
                    execution_time = await execute_timing_query(timing_query_sql, conn_params)

                    # Getting perf coeff from manifest (default 1.0)
                    performance_coefficient = manifest.performance_coefficient

                    # Getting expected time with a perfomance coefficient
                    expected_time_ms = timing_query.expected_time_ms
                    adjusted_expected_time_ms = expected_time_ms / performance_coefficient

                    # Matching a time of query with time_expected
                    if execution_time * 1000 <= adjusted_expected_time_ms:
                        logger.info(
                            f"Execution time {execution_time * 1000:.2f}ms is within expected time {adjusted_expected_time_ms:.2f}ms for {case_name}")
                        timing_result = 'within expected'
                    else:
                        logger.warning(
                            f"Execution time {execution_time * 1000:.2f}ms exceeds expected time {adjusted_expected_time_ms:.2f}ms for {case_name}")
                        timing_result = 'exceeds expected'

                    # Saving result to common results
                    case_result['timing_results'].append({
                        'query': timing_query.query,
                        'result': timing_result,
                        'execution_time_ms': execution_time * 1000,
                        'expected_time_ms': adjusted_expected_time_ms, # Save exc. time with perf coeff of machine (def. 1.0 * exc. time)
                        'status': 'success' if timing_result == 'within expected' else 'failure'
                    })

            if case.post_hook:
                post_hook_path = os.path.join(case_dir, case.post_hook)
                if os.path.isfile(post_hook_path):
                    logger.info(f"Executing post_hook for {case_name}")
                    container_post_hook_path = f"/scenario/cases/{case_name}/{case.post_hook}"
                    if case.post_hook.endswith('.sh'):
                        command = f"bash {container_post_hook_path}"
                    elif case.post_hook.endswith('.py'):
                        command = f"python {container_post_hook_path}"
                    else:
                        logger.warning(f"Unknown post_hook file type for {case_name}: {case.post_hook}")
                        continue
                    docker_manager.exec_command(command)
                    logger.info(f"Executed post_hook for {case_name}")
                else:
                    logger.error(f"post_hook file does not exist for {case_name}: {post_hook_path}")

            # Added result in results of case_*
            test_result['cases'].append(case_result)

        # docker_manager.stop_container()
        logger.info(f"Container {docker_manager.container_name} stopped and removed")

        # Added results
        test_results.append(test_result)

        print_test_results(test_results, test.db_type)

    return test_results

async def wait_for_db_ready(host, port, user, retries=5, delay=2):
    for i in range(retries):
        try:
            conn = await asyncpg.connect(host=host, port=port, user=user)
            await conn.close()
            return True
        except Exception as e:
            logger.info(f"Database not ready yet ({e}), retrying in {delay} seconds...")
            await asyncio.sleep(delay)
    raise Exception("Database is not ready after multiple retries")

async def execute_explain_query(query_sql, conn_params):
    # Add EXPLAIN (VERBOSE, COSTS OFF) before each explain query
    explain_query = f'EXPLAIN (VERBOSE, COSTS OFF) {query_sql}'
    conn = await asyncpg.connect(**conn_params)
    try:
        records = await conn.fetch(explain_query)
        # Getting execution plan
        explain_plan_lines = [record['QUERY PLAN'] for record in records]
        # Filter 'Query Identifier'
        explain_plan_lines = [line for line in explain_plan_lines if not line.startswith('Query Identifier:')]
        explain_plan = '\n'.join(explain_plan_lines)
        return explain_plan
    finally:
        await conn.close()


async def execute_timing_query(query_sql, conn_params):
    conn = await asyncpg.connect(**conn_params)
    try:
        start_time = time.perf_counter()
        await conn.execute(query_sql)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        return execution_time
    finally:
        await conn.close()


def print_test_results(test_results, releases):
    # ANSI escape codes for colors (optional)
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'

    for test_result in test_results:
        print("=" * 80)
        print(f"Database Version: {test_result['test_version']}, Database Type: {releases}")
        print("=" * 80)
        for case in test_result['cases']:
            print(f"Case: {case['case_name']}")
            # Pre Hook Result
            if case.get('pre_hook_result'):
                print(f"  Pre Hook Result: {case['pre_hook_result']}")
            # Explain Results
            if case['explain_results']:
                print("  Explain Queries:")
                for explain_result in case['explain_results']:
                    result_color = GREEN if explain_result['result'] == 'match' else RED
                    icon = '✔️' if explain_result['result'] == 'match' else '❌'
                    print(f"    Query: {explain_result['query']}")
                    print(f"    Result: {result_color}{icon} {explain_result['result'].capitalize()}{RESET}")
                    if explain_result['result'] == 'no match':
                        print("    Actual Explain Plan:")
                        print(explain_result['actual_plan'])
                        print("    Expected Explain Plans:")
                        for expected_file_name, expected_plan in explain_result['expected_plans']:
                            print(f"      From {expected_file_name}:")
                            print(expected_plan)
            # Timing Results
            if case['timing_results']:
                print("  Timing Queries:")
                for timing_result in case['timing_results']:
                    result_color = GREEN if timing_result['result'] == 'within expected' else RED
                    icon = '✔️' if timing_result['result'] == 'within expected' else '❌'
                    print(f"    Query: {timing_result['query']}")
                    print(f"    Result: {result_color}{icon} {timing_result['result'].capitalize()}{RESET}")
                    print(f"{'    Execution Time:':25}{timing_result['execution_time_ms']:.2f} ms")
                    print(f"{'    Expected Time (adjusted):':25}{timing_result['expected_time_ms']:.2f} ms")
            # Post Hook Result
            if case.get('post_hook_result'):
                print(f"  Post Hook Result: {case['post_hook_result']}")
            print("-" * 80)
        print()

