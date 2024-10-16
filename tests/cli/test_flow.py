import datetime

import pytest

from syntask.client.orchestration import SyntaskClient
from syntask.testing.cli import invoke_and_assert
from syntask.testing.utilities import AsyncMock
from syntask.utilities.asyncutils import run_sync_in_worker_thread


class TestFlowServe:
    """
    These tests ensure that the `syntask flow serve` interacts with Runner
    in the expected way. Behavior such as flow run
    execution and cancellation are tested in test_runner.py.
    """

    @pytest.fixture
    async def mock_runner_start(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr("syntask.cli.flow.Runner.start", mock)
        return mock

    def test_flow_serve_cli_requires_entrypoint(self):
        invoke_and_assert(
            command=["flow", "serve"],
            expected_code=2,
            expected_output_contains=[
                "Missing argument 'ENTRYPOINT'.",
            ],
        )

    async def test_flow_serve_cli_creates_deployment(
        self, syntask_client: SyntaskClient, mock_runner_start: AsyncMock
    ):
        await run_sync_in_worker_thread(
            invoke_and_assert,
            command=["flow", "serve", "flows/hello_world.py:hello", "--name", "test"],
            expected_code=0,
            expected_output_contains=[
                "Your flow 'hello' is being served and polling for scheduled runs!",
                "To trigger a run for this flow, use the following command",
                "$ syntask deployment run 'hello/test'",
            ],
        )

        deployment = await syntask_client.read_deployment_by_name(name="hello/test")

        assert deployment is not None
        assert deployment.name == "test"
        assert deployment.entrypoint == "flows/hello_world.py:hello"

        mock_runner_start.assert_called_once()

    async def test_flow_serve_cli_accepts_interval(
        self, syntask_client: SyntaskClient, mock_runner_start
    ):
        await run_sync_in_worker_thread(
            invoke_and_assert,
            command=[
                "flow",
                "serve",
                "flows/hello_world.py:hello",
                "--name",
                "test",
                "--interval",
                "3600",
            ],
            expected_code=0,
        )

        deployment = await syntask_client.read_deployment_by_name(name="hello/test")

        assert len(deployment.schedules) == 1
        schedule = deployment.schedules[0].schedule
        assert schedule.interval == datetime.timedelta(seconds=3600)

    async def test_flow_serve_cli_accepts_cron(
        self, syntask_client: SyntaskClient, mock_runner_start
    ):
        await run_sync_in_worker_thread(
            invoke_and_assert,
            command=[
                "flow",
                "serve",
                "flows/hello_world.py:hello",
                "--name",
                "test",
                "--cron",
                "* * * * *",
            ],
            expected_code=0,
        )

        deployment = await syntask_client.read_deployment_by_name(name="hello/test")
        assert len(deployment.schedules) == 1
        assert deployment.schedules[0].schedule.cron == "* * * * *"

    async def test_flow_serve_cli_accepts_rrule(
        self, syntask_client: SyntaskClient, mock_runner_start
    ):
        await run_sync_in_worker_thread(
            invoke_and_assert,
            command=[
                "flow",
                "serve",
                "flows/hello_world.py:hello",
                "--name",
                "test",
                "--rrule",
                "FREQ=MINUTELY;COUNT=5",
            ],
            expected_code=0,
        )

        deployment = await syntask_client.read_deployment_by_name(name="hello/test")
        assert len(deployment.schedules) == 1
        assert deployment.schedules[0].schedule.rrule == "FREQ=MINUTELY;COUNT=5"

    async def test_flow_serve_cli_accepts_metadata_fields(
        self, syntask_client: SyntaskClient, mock_runner_start
    ):
        await run_sync_in_worker_thread(
            invoke_and_assert,
            command=[
                "flow",
                "serve",
                "flows/hello_world.py:hello",
                "--name",
                "test",
                "--description",
                "test description",
                "--tag",
                "test",
                "--tag",
                "test2",
                "--version",
                "1.0.0",
            ],
            expected_code=0,
        )

        deployment = await syntask_client.read_deployment_by_name(name="hello/test")

        assert deployment.description == "test description"
        assert deployment.tags == ["test", "test2"]
        assert deployment.version == "1.0.0"
