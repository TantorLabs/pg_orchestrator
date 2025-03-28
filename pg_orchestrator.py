import argparse
import pprint
import asyncio
import os

from src.manifest import read_migration_manifest
from src.logger import logger
from perf.perf import *
from upgrade.upgrade import *

# Define global version
PG_ORCHESTRATOR_VERSION = "1.0.0"

def log_application_info():
    # Log the application name and version
    logger.info(f"--- PG_ORCHESTRATOR VERSION: {PG_ORCHESTRATOR_VERSION} ---")

def get_args():
    description_text = (
        "pg_orchestrator - a tool for running database migration and performance tests.\n\n"
        "Usage: provide the --scenario flag with the name of the scenario directory.\n"
        "The scenario directory should contain a configuration file named conf.yaml.\n"
        "If no arguments are provided, help and a list of available scenarios will be displayed."
    )

    epilog_text = (
        "Note: If the configuration specifies db_type 'ttdb', you must set the following environment variables:\n"
        "  NEXUS_USER\n"
        "  NEXUS_USER_PASSWORD\n"
        "  NEXUS_URL\n"
        "For example:\n"
        "  export NEXUS_USER='your_username'\n"
        "  export NEXUS_USER_PASSWORD='your_password'\n"
        "  export NEXUS_URL='your_nexus_url'\n\n"
        "For db_type 'pgdg', these variables are not required."
    )

    parser = argparse.ArgumentParser(
        description=description_text,
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--scenario', type=str, required=True, help="Name of the scenario directory")
    args = parser.parse_args()

    # Check if the scenario directory exists
    scenario_path = os.path.join('items', args.scenario)
    if not os.path.isdir(scenario_path):
        # Get the list of available scenarios
        available_scenarios = [d for d in os.listdir('items') if os.path.isdir(os.path.join('items', d))]
        print("You must input the scenario name, example: ", ', '.join(available_scenarios))
        parser.exit(1)
    args.scenario = scenario_path

    # Check if the scenario configuration file conf.yaml exists
    config_file = os.path.join(args.scenario, 'conf.yaml')
    if not os.path.isfile(config_file):
        print(f"The configuration file 'conf.yaml' does not exist in the scenario directory {args.scenario}")
        parser.exit(1)
    args.manifest = config_file

    # Log all arguments
    logger.info("Arguments provided:")
    for arg, value in vars(args).items():
        logger.info(f"{arg}: {value}")

    return args

def get_migration_manifest(path):
    with open(path, 'r') as file:
        # with scenario (update or perf)
        manifest = read_migration_manifest(file)

        # Log all yaml contents
        logger.info(f"\n--- Manifest Kind:{manifest.kind} ---")
        logger.info(pprint.pformat(manifest.dict() if hasattr(manifest, 'dict') else manifest))
        logger.info("--- End of Manifest ---\n")

        return manifest

def main():
    log_application_info()

    args = get_args()

    manifest = get_migration_manifest(args.manifest)

    # Check --scenario [update,perf?]
    if manifest.kind == 'upgrade':
        print("Starting migration tests")
        run_upgrade(manifest, args.scenario)
    elif manifest.kind == 'perf':
        # Call for the perf scenario
        print("Will be started performance tests")
        asyncio.run(run_perf(manifest, args.scenario))
    else:
        raise ValueError("Unknown scenario, must be 'upgrade' or 'perf'")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print('Error while executing program')
        print(e)
