import pytest

from syntask.events import Event
from syntask.settings import (
    SYNTASK_API_KEY,
    SYNTASK_API_URL,
    SYNTASK_CLOUD_API_URL,
    temporary_settings,
)
from syntask.testing.cli import invoke_and_assert
from syntask.testing.fixtures import Puppeteer
from syntask.utilities.asyncutils import run_sync_in_worker_thread


@pytest.fixture
def example_event_1() -> Event:
    return Event(
        event="marvelous.things.happened",
        resource={"syntask.resource.id": "something-valuable"},
        related=[
            {
                "syntask.resource.role": "actor",
                "syntask.resource.id": "syntask-cloud.actor.5c83c6e4-3a6b-42db-93b1-b81d2773a0ec",
                "syntask.resource.name": "Peter Francis Geraci",
                "syntask-cloud.email": "george@khulnasoft.com",
                "syntask-cloud.name": "George Coyne",
                "syntask-cloud.handle": "georgesyntaskio",
            }
        ],
    )


@pytest.fixture
def example_event_2() -> Event:
    return Event(
        event="wondrous.things.happened",
        resource={"syntask.resource.id": "something-valuable"},
    )


@pytest.fixture
def cloud_api_setup(events_cloud_api_url: str):
    with temporary_settings(
        updates={
            SYNTASK_API_URL: events_cloud_api_url,
            SYNTASK_API_KEY: "my-token",
            SYNTASK_CLOUD_API_URL: events_cloud_api_url,
        }
    ):
        yield


@pytest.mark.usefixtures("cloud_api_setup")
async def test_stream_workspace(
    example_event_1: Event,
    example_event_2: Event,
    puppeteer: Puppeteer,
):
    puppeteer.outgoing_events = [example_event_1, example_event_2]
    puppeteer.token = "my-token"

    event_stream = await run_sync_in_worker_thread(
        invoke_and_assert,
        [
            "events",
            "stream",
            "--run-once",
        ],
        expected_code=0,
        expected_output_contains=[
            "Subscribing to event stream...",
            "wondrous.things.happened",
            "something-valuable",
        ],
    )
    stdout_list = event_stream.stdout.strip().split("\n")
    assert len(stdout_list) == 3
    event1 = stdout_list[1]
    try:
        parsed_event = Event.model_validate_json(event1)
        assert parsed_event.event == example_event_1.event
    except ValueError as e:
        pytest.fail(f"Failed to parse event: {e}")


@pytest.mark.usefixtures("cloud_api_setup")
async def test_stream_account(
    example_event_1: Event,
    example_event_2: Event,
    puppeteer: Puppeteer,
):
    puppeteer.outgoing_events = [example_event_1, example_event_2]
    puppeteer.token = "my-token"

    event_stream = await run_sync_in_worker_thread(
        invoke_and_assert,
        [
            "events",
            "stream",
            "--account",
            "--run-once",
        ],
        expected_code=0,
        expected_output_contains=[
            "Subscribing to event stream...",
            "marvelous.things.happened",
            "something-valuable",
        ],
    )
    stdout_list = event_stream.stdout.strip().split("\n")
    assert len(stdout_list) == 3
    event1 = stdout_list[1]
    try:
        parsed_event = Event.model_validate_json(event1)
        assert parsed_event.event == example_event_1.event
    except ValueError as e:
        pytest.fail(f"Failed to parse event: {e}")


@pytest.fixture
def oss_api_setup(events_api_url: str):
    with temporary_settings(
        updates={
            SYNTASK_API_URL: events_api_url,
            SYNTASK_API_KEY: None,
        }
    ):
        yield


@pytest.mark.usefixtures("oss_api_setup")
async def test_stream_oss_events(
    example_event_1: Event,
    example_event_2: Event,
    puppeteer: Puppeteer,
):
    puppeteer.outgoing_events = [example_event_1, example_event_2]
    puppeteer.token = None

    event_stream = await run_sync_in_worker_thread(
        invoke_and_assert,
        [
            "events",
            "stream",
            "--run-once",
        ],
        expected_code=0,
        expected_output_contains=[
            "Subscribing to event stream...",
            "wondrous.things.happened",
            "something-valuable",
        ],
    )

    stdout_list = event_stream.stdout.strip().split("\n")
    assert len(stdout_list) == 3

    event1 = stdout_list[1]
    try:
        parsed_event = Event.model_validate_json(event1)
        assert parsed_event.event == example_event_1.event
    except ValueError as e:
        pytest.fail(f"Failed to parse event: {e}")
