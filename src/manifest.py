from enum import Enum
import yaml
from pydantic import BaseModel, ConfigDict, field_validator, Field
from typing import Union, List, Optional

ScriptList = Union[str, List[str], None]
kind_options = ['upgrade', 'perf']

####################
# For Common Use
####################

class DockerConfig(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    image: str
    """Docker image to be used, e.g., 'tt_build_ubuntu:22.04'."""

    registry: Optional[str] = None
    """Docker registry URL, e.g., 'registry.lala.com'."""

    host_port: Optional[int] = None
    """The host port to be mapped to the container port, e.g., 5430."""

    container_port: Optional[int] = None
    """The container port that will be exposed, e.g., 5432."""

    container_name: Optional[str] = None
    """The name of the Docker container, e.g., 'pg_orchestrator_container'."""



####################
# For Upgrade Use
####################
class MigrationStrategy(str, Enum):
    PG_DUMPALL = 'pg_dumpall'
    PG_UPGRADE = 'pg_upgrade'
    MINOR = 'minor'

class MigrationStep(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    type: MigrationStrategy
    """
    Strategy of migration
    """

    db_version: str
    """
    Target version of database we want to migrate
    """

    db_edition: Optional[str] = None
    """
    Target TantorDB edition
    """

    package: Optional[str] = None
    """
    Optional we can install postgres from deb package!
    """

    pre_scripts: ScriptList = None
    """
    Scripts that run before migration, but after 'initdb'
    """

    post_scripts: ScriptList = None
    """
    Scripts that run after migration
    """

    verifiers: ScriptList = None
    """
    Scripts that run last and must check database integrity
    """

    args: dict[str, str | list[str] | None] = None
    """
    Additional arguments for binary files run on this step
    """

class MigrationManifest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    kind: str
    """Type of the scenario, e.g., 'perf' or 'update'."""

    @field_validator('kind')
    def validate_kind(cls, value):
        if value not in kind_options:
            raise ValueError(f"Invalid kind: '{value}'. Must be one of: {kind_options}")
        return value

    steps: list[MigrationStep]
    """
    Migration steps
    """

    db_type: str
    """
    DB type. ttdb or pgdg.
    ttdb - Tantor database.
    pgdg - PostgreSQL originally database.
    """

    db_version: str
    """
    Initial version of database we want to migrate
    """

    db_edition: Optional[str] = None
    """
    DB edition.
    """

    package: Optional[str] = None
    """
    Optional we can install postgres from deb package!
    """

    initial_setup_script: Optional[str] = None
    """
    Additional script that runs immediately after the database initialization,
    before executing migration steps. It can be a SQL (.sql), shell (.sh), or Python (.py) file.
    The script must be located in the scripts directory.
    """

    initial_pre_scripts: ScriptList = None
    """Scripts for executing before MINOR stage will executing"""

    initial_post_scripts: ScriptList = None
    """Scripts for executing after MINOR stage will executed"""

    pre_scripts: ScriptList = None
    """
    Scripts that run before migration, but after 'initdb'.
    Step pre_scripts override this      SQL/SHELL
    """

    post_scripts: ScriptList = None
    """
    Scripts that run after migration.
    Step post_scripts override this     SQL/SHELL
    """

    verifiers: ScriptList = None
    """
    Scripts that run last and must check database integrity.
    Step verifier override this
    """

    args: dict[str, str | list[str]] | None = None
    """
    Additional arguments for binary files.
    They will be applied if step did not specify them.
    """

    docker: DockerConfig
    """Docker configuration."""

####################
# For Perfomance Use
####################

class ExplainQuery(BaseModel):
    query: str
    """Path to the SQL file containing the explain query."""

    expected: List[str]
    """List of paths to the files containing expected explain plans."""

class TimingQuery(BaseModel):
    query: str
    """Path to the SQL file containing the timing query."""

    expected_time_ms: float
    """Expected execution time in milliseconds."""

class Case(BaseModel):
    name: str
    """Name of the case, e.g., 'case_1'."""

    pre_hook: Optional[str] = None
    """Optional script to run before the case, e.g., 'pre_hook.sh' or 'pre_hook.py'."""

    post_hook: Optional[str] = None
    """Optional script to run after the case, e.g., 'post_hook.sh' or 'post_hook.py'."""

    explain_queries: Optional[List[ExplainQuery]] = None
    """List of explain queries and their expected plans."""

    timing_queries: Optional[List[TimingQuery]] = None
    """List of timing queries and their expected execution times in milliseconds."""

class DBParam(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    db_type: str
    """Type of the database, e.g., 'ttdb' or 'pgdg'."""

    db_version: str
    """Version of the database, e.g., '15.6.1'."""

    db_port: int
    """Port number for the database."""

    db_edition: Optional[str] = None
    """Edition of the database, e.g., 'se-1c'. This field is optional."""

    @property
    def db_major_version(self) -> str:
        """Extracts and returns the major version from db_version."""
        return self.db_version.split('.')[0]

    @property
    def pgdg_maintanance_version(self) -> str:
        """Extracts and returns the major version from db_version."""
        return self.db_version.split('.')[0] + '.' + self.db_version.split('.')[1]

class PerformanceManifest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    kind: str
    """Type of the scenario, e.g., 'perf' or 'update'."""

    @field_validator('kind')
    def validate_kind(cls, value):
        if value not in kind_options:
            raise ValueError(f"Invalid kind: '{value}'. Must be one of: {kind_options}")
        return value

    db_params: List[DBParam]
    """List of database parameters."""

    db_initial_script: str
    """Initial script to populate the database, e.g., 'fill_db.sh'."""

    initial_script: Optional[str] = None
    """Optional script (sh or py) that will be executed before modifying postgresql.conf.
    e.g. for installing some extensions and add this extension to shared preload libraries especially"""

    configuration: Optional[str] = None
    """Configuration file for PostgreSQL, e.g., '1c.conf', '2.conf'."""

    docker: DockerConfig
    """Docker configuration."""

    cases: List[Case]
    """List of test cases."""

    performance_coefficient: float = Field(1.0, ge=0.1, le=1.0)
    """Performance coefficient between 0.1 and 1.0, where 1.0 is the fastest system."""

####################
# Main function
####################

def read_migration_manifest(file):
    obj = yaml.safe_load(file)

    if obj.get('kind') == 'perf':
        return PerformanceManifest(**obj)
    elif obj.get('kind') == 'upgrade':
        return MigrationManifest(**obj)
    else:
        raise ValueError("Unknown kind in manifest, must be 'update' or 'perf'")
