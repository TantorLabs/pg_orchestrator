import os
import docker
from docker.errors import NotFound, DockerException
import getpass
import json
import sys
import io
import shlex
from typing import NamedTuple
from src.logger import *

class ExecResult(NamedTuple):
    exit_code: int
    output: str

class DockerContainerManager:
    def __init__(self, image_name: str, container_name: str, environment_vars: dict = None, volumes: dict = None, registry_url: str = None, host_port: int = 5552, container_port: int = 5432, use_host_network: bool = False):
        try:
            self.client = docker.from_env()
        except DockerException as e:
            logger.error("Failed to connect to Docker daemon.")
            logger.error("Ensure that your user has permission to access the Docker daemon.")
            logger.error("You can add your user to the 'docker' group using:")
            logger.error("  sudo usermod -aG docker $USER")
            logger.error("Then log out and log back in to apply the changes.")
            logger.debug(f"Original error: {e}")
            sys.exit(1)

        self.container = None
        self.image_name = image_name
        self.container_name = container_name
        self.environment_vars = environment_vars  # Store environment variables
        self.volumes = volumes or {}  # Store mounted directories, if provided
        self.registry_url = registry_url  # Docker registry URL for login
        self.host_port = host_port  # Port on the host machine to map
        self.container_port = container_port  # Port inside the container (default is 5432 for PostgreSQL)
        self.use_host_network = use_host_network  # Whether to use host network mode

        # Check if the container exists and handle image pulling if necessary
        self.check_and_remove_existing_container()

    def check_docker_login_status(self):
        """
        Check if the user is already logged in to the registry by inspecting the ~/.docker/config.json file.
        Return True if the user is logged in, False otherwise.
        """
        docker_config_path = os.path.expanduser("~/.docker/config.json")
        if os.path.exists(docker_config_path):
            with open(docker_config_path, 'r') as f:
                docker_config = json.load(f)
                auths = docker_config.get("auths", {})
                # Check if registry URL is in the list of authenticated registries
                return self.registry_url in auths
        return False

    def check_image_exists_or_pull(self):
        """
        Check if the image exists locally. If not, prompt for login credentials and pull the image.
        """
        try:
            # Try to find the image locally
            self.client.images.get(self.image_name)
            print(f"Image '{self.image_name}' found locally.")
        except docker.errors.ImageNotFound:
            # If the image is not found locally, prompt for login credentials if a registry URL is provided
            if self.registry_url != 'None' :
                if self.check_docker_login_status():
                    print(f"Already logged in to {self.registry_url}. No need to log in again.")
                else:
                    print(f"Image '{self.image_name}' not found. Please log in to the registry at {self.registry_url}.")

                    username = input("Enter Docker registry username: ")
                    password = getpass.getpass("Enter Docker registry password: ")

                    # Perform docker login
                    print(f"Logging in to Docker registry at {self.registry_url}...")
                    self.client.login(username=username, password=password, registry=self.registry_url)
                    print(f"Login to {self.registry_url} successful.")

            # Pull the image from the registry
            pull_output = self.client.api.pull(self.image_name, stream=True, decode=True)
            last_status = None
            for line in pull_output:
                status = line.get('status')
                progress = line.get('progress', '')
                # Only print changes in status to reduce verbosity
                if status != last_status:
                    print(f"{status} {progress}")
                    last_status = status
                elif progress:
                    sys.stdout.write(f"\r{status} {progress}")  # Overwrite the current line with progress
                    sys.stdout.flush()

            print(f"\nImage '{self.image_name}' pulled successfully.")
        except Exception as e:
            print(f"An error occurred while checking or pulling the image: {e}")

    def check_and_remove_existing_container(self):
        """
        Check if the container exists. If not, check the image and pull it if necessary.
        """
        try:
            # Check if a container with the same name exists
            existing_container = self.client.containers.get(self.container_name)
            print(f"Container {self.container_name} exists. Stopping and removing...")
            existing_container.stop()
            existing_container.remove()
            print(f"Container {self.container_name} successfully removed.")
        except NotFound:
            # If the container with that name is not found, check the image and pull if necessary
            print(f"Container {self.container_name} not found. Checking for the image...")
            self.check_image_exists_or_pull()

    def start_container(self):
        try:
            network_mode = "host" if self.use_host_network else None
            self.container = self.client.containers.run(
                self.image_name,
                name=self.container_name,
                command="/bin/sh",
                detach=True,
                stdin_open=True,
                tty=True,
                volumes=self.volumes,
                environment=self.environment_vars,
                ports={f'{self.container_port}/tcp': self.host_port} if not self.use_host_network else None,
                # Port forwarding only if not in host network mode
                network_mode=network_mode  # Use host network mode if specified
            )
            print(f"Container {self.container.short_id} with name {self.container_name} started.")
            print(f"Port {self.host_port} on the host is mapped to port {self.container_port} in the container.")

        except docker.errors.ContainerError as e:
            # print(f"Error: The container '{self.container_name}' failed to start.")
            # print(f"Details: {str(e)}")
            logger.error(f"Error: The container '{self.container_name}' failed to start. \nDetails: {str(e)}")
        except docker.errors.APIError as e:
            logger.error(f"API error during container start: {e}")

    def stop_container(self):
        if self.container:  # Ensure container is initialized before stopping
            try:
                self.container.stop()
                self.container.remove()
                print(f"Container {self.container.short_id} stopped and removed.")
            except docker.errors.APIError as e:
                logger.error(f"Error stopping or removing container '{self.container_name}': {e}")

    def exec_command(self, command, log_to_file=False):
        """
        Execute a command inside a Docker container. Output can be redirected to a log file if log_to_file is True.
        """
        log_file = None
        if log_to_file:
            log_directory = os.path.join(os.getcwd(), 'logs')
            os.makedirs(log_directory, exist_ok=True)
            log_file_name = f"perf_dbms_{TIMESTAMP}.log"
            log_file_path = os.path.join(log_directory, log_file_name)
            file_already_exists = os.path.exists(log_file_path)
            log_file = open(log_file_path, 'a')
            if not file_already_exists:
                logger.info(f"Logging Docker command output to {log_file_name} in 'log' directory")

        try:
            if isinstance(command, str):
                exec_id = self.container.client.api.exec_create(self.container.id, command, tty=True)
                output = self.container.client.api.exec_start(exec_id, tty=True, stream=True)
                self._write_output(output, log_file)

                # Inspect command execution result
                resp = self.container.client.api.exec_inspect(exec_id)
                exit_code = resp['ExitCode']

                if exit_code != 0:
                    # Skipping 127 from db_installer.sh, because systemctl not using in containers
                    if "db_installer.sh" in command and exit_code == 127:
                        logger.warning("Ignoring error code 127 from db_installer.sh due to missing systemctl")
                        exit_code = 0
                    else:
                        error_message = f"Command '{command}' failed with exit code {exit_code}."
                        logger.error(error_message)

                return exit_code
        except Exception as e:
            print(f"Error during command execution: {e}")
        finally:
            if log_file:
                log_file.close()

    def _write_output(self, output, log_file):
        """
        Helper method to write output to terminal or log file.
        """
        for chunk in output:
            if log_file:
                log_file.write(chunk.decode('utf-8'))
                log_file.flush()
            else:
                sys.stdout.buffer.write(chunk)
                sys.stdout.flush()

    def shell(self, *command: str, env=None, logfile: str | io.TextIOBase = None, cwd: str = None,
              check_code=True) -> ExecResult:
        try:
            cmd = shlex.join(command)
            logger.debug('Executing command in container: %s', cmd)

            exec_id = self.container.client.api.exec_create(self.container.id, cmd, environment=env, workdir=cwd, tty=True)
            output_stream = self.container.client.api.exec_start(exec_id, tty=True, stream=True)

            contents = ""

            for chunk in output_stream:
                decoded = chunk.decode('utf-8')
                contents += decoded
                if logfile:
                    if isinstance(logfile, str):
                        with open(logfile, 'a') as file:
                            file.write(decoded)
                            file.flush()
                    else:
                        logfile.write(decoded)
                        logfile.flush()
                # else:
                #     sys.stdout.write(decoded)
                #     sys.stdout.flush()

            # Get exec code
            resp = self.container.client.api.exec_inspect(exec_id)
            exit_code = resp['ExitCode']
            if check_code and exit_code != 0:
                logger.error('Command failed with exit code %s: %s', exit_code, cmd)
                raise RuntimeError(f'Command failed with exit code {exit_code}: {cmd}')
            return ExecResult(exit_code, contents)
        except Exception as e:
            logger.exception('An error occurred while executing the command: %s', cmd)
            raise
