import unittest
from unittest.mock import patch, MagicMock
from src.logger import *
from docker.errors import NotFound, ImageNotFound, DockerException, ContainerError, APIError
from manager.dockerManager import DockerContainerManager

class TestDockerContainerManager(unittest.TestCase):
    def setUp(self):
        self.image_name = 'gitlab.tantorlabs.ru:6000/devops/build/db-build-image/tt_build_ubuntu:22.04'
        self.container_name = 'test_container'
        self.environment_vars = {'ENV_VAR': 'value'}
        self.volumes = {'/tmp/gov': {'bind': '/container/path', 'mode': 'rw'}}
        self.registry_url = 'gitlab.tantorlabs.ru:6000'
        self.host_port = 1234
        self.container_port = 4321
        self.use_host_network = False

        # Mock docker.from_env()
        patcher = patch('docker.from_env')
        self.addCleanup(patcher.stop)
        self.mock_docker_from_env = patcher.start()
        self.mock_client = MagicMock()
        self.mock_docker_from_env.return_value = self.mock_client

    def test_init_success(self):
        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name,
            environment_vars=self.environment_vars,
            volumes=self.volumes,
            registry_url=self.registry_url,
            host_port=self.host_port,
            container_port=self.container_port,
            use_host_network=self.use_host_network
        )

        self.assertEqual(manager.image_name, self.image_name)
        self.assertEqual(manager.container_name, self.container_name)
        self.assertEqual(manager.environment_vars, self.environment_vars)
        self.assertEqual(manager.volumes, self.volumes)
        self.assertEqual(manager.registry_url, self.registry_url)
        self.assertEqual(manager.host_port, self.host_port)
        self.assertEqual(manager.container_port, self.container_port)
        self.assertEqual(manager.use_host_network, self.use_host_network)
        self.assertIsNotNone(manager.client)

    def test_init_docker_exception(self):
        self.mock_docker_from_env.side_effect = DockerException("Docker daemon not found")
        with self.assertRaises(SystemExit):
            DockerContainerManager(
                image_name=self.image_name,
                container_name=self.container_name
            )

    def test_check_and_remove_existing_container_container_exists(self):
        # Mock the existence of the container
        mock_container = MagicMock()
        self.mock_client.containers.get.return_value = mock_container

        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )

        # Check that the container is stopped and removed
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()

    def test_check_and_remove_existing_container_container_not_found(self):
        # Mock the absence of the container
        self.mock_client.containers.get.side_effect = NotFound("Container not found")

        # Mock the method check_image_exists_or_pull
        with patch.object(DockerContainerManager, 'check_image_exists_or_pull') as mock_check_image:
            manager = DockerContainerManager(
                image_name=self.image_name,
                container_name=self.container_name
            )

            mock_check_image.assert_called_once()
    def test_check_image_exists_or_pull_image_exists(self):
        # Mock the existence of the image
        self.mock_client.images.get.return_value = MagicMock()

        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )

        manager.check_image_exists_or_pull()

        # Check that the image is not being pulled
        self.mock_client.images.get.assert_called_with(self.image_name)
        self.mock_client.api.pull.assert_not_called()

    def test_check_image_exists_or_pull_image_not_found_no_registry(self):
        # Mock the absence of the image
        self.mock_client.images.get.side_effect = ImageNotFound("Image not found")
        # Set registry_url to None
        manager = DockerContainerManager(
            image_name='None',
            container_name=self.container_name,
            registry_url='None'
        )

        manager.check_image_exists_or_pull()


        # Check that the image is attempted to be pulled
        self.mock_client.api.pull.assert_called_with('None', stream=True, decode=True)

    def test_start_container_success(self):
        mock_container = MagicMock()
        self.mock_client.containers.run.return_value = mock_container

        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name,
            environment_vars=self.environment_vars,
            volumes=self.volumes,
            host_port=self.host_port,
            container_port=self.container_port,
            use_host_network=self.use_host_network
        )

        manager.start_container()

        self.mock_client.containers.run.assert_called_with(
            self.image_name,
            name=self.container_name,
            command="/bin/sh",
            detach=True,
            stdin_open=True,
            tty=True,
            volumes=self.volumes,
            environment=self.environment_vars,
            ports={f'{self.container_port}/tcp': self.host_port},
            network_mode=None
        )

    def test_start_container_container_error(self):
        self.mock_client.containers.run.side_effect = ContainerError(
            container=None, exit_status=1, command='run', image=self.image_name, stderr='Error'
        )

        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )

        with self.assertLogs(logger, level='ERROR') as log:
            manager.start_container()

        self.assertIn("Error: The container 'test_container' failed to start.", log.output[0])

    def test_exec_command_success(self):
        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )

        manager.container = MagicMock()
        manager.container.client = MagicMock()
        manager.container.client.api.exec_create.return_value = 'exec_id'
        manager.container.client.api.exec_start.return_value = [b'output']
        manager.container.client.api.exec_inspect.return_value = {'ExitCode': 0}

        exit_code = manager.exec_command('ls -la')

        self.assertEqual(exit_code, 0)
        manager.container.client.api.exec_create.assert_called_once()
        manager.container.client.api.exec_start.assert_called_once_with('exec_id', tty=True, stream=True)

    def test_exec_command_failure(self):
        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )

        manager.container = MagicMock()
        manager.container.client = MagicMock()
        manager.container.client.api.exec_create.return_value = 'exec_id'
        manager.container.client.api.exec_start.return_value = [b'error']
        manager.container.client.api.exec_inspect.return_value = {'ExitCode': 1}

        with self.assertLogs(logger, level='ERROR') as log:
            exit_code = manager.exec_command('ls -la')
            self.assertEqual(exit_code, 1)
            self.assertIn("Command 'ls -la' failed with exit code 1.", log.output[0])

    def test_stop_container_success(self):
        mock_container = MagicMock()
        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )
        manager.container = mock_container

        manager.stop_container()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()

    def test_stop_container_no_container(self):
        manager = DockerContainerManager(
            image_name=self.image_name,
            container_name=self.container_name
        )
        manager.container = None

        # Check that the method does not crash
        manager.stop_container()
