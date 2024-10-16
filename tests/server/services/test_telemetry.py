import json
import platform

import pytest
import respx
from httpx import Response

import syntask
from syntask.server.services.telemetry import Telemetry


@pytest.fixture
def sens_o_matic_mock():
    with respx.mock:
        sens_o_matic = respx.post(
            "https://sens-o-matic.syntask.khulnasoft.com/",
        ).mock(return_value=Response(200, json={}))

        yield sens_o_matic


@pytest.fixture
def error_sens_o_matic_mock():
    with respx.mock:
        sens_o_matic = respx.post(
            "https://sens-o-matic.syntask.khulnasoft.com/",
        ).mock(return_value=Response(500, json={}))

        yield sens_o_matic


async def test_sens_o_matic_called_correctly(sens_o_matic_mock):
    from syntask.client.constants import SERVER_API_VERSION

    telemetry = Telemetry()
    await telemetry.start(loops=1)

    assert sens_o_matic_mock.called
    assert sens_o_matic_mock.call_count == 1

    request = sens_o_matic_mock.calls[0].request
    assert request.headers["x-syntask-event"] == "syntask_server"

    heartbeat = json.loads(request.content.decode("utf-8"))
    assert heartbeat["type"] == "heartbeat"
    assert heartbeat["source"] == "syntask_server"

    payload = heartbeat["payload"]
    assert payload["platform"] == platform.system()
    assert payload["architecture"] == platform.machine()
    assert payload["python_version"] == platform.python_version()
    assert payload["python_implementation"] == platform.python_implementation()

    assert payload["api_version"] == SERVER_API_VERSION
    assert payload["syntask_version"] == syntask.__version__

    assert payload["session_id"] == telemetry.session_id
    assert payload["session_start_timestamp"] == telemetry.session_start_timestamp


async def test_sets_and_fetches_session_information(sens_o_matic_mock):
    telemetry = Telemetry()
    await telemetry.start(loops=1)

    # set it on the first call
    sid = telemetry.session_id
    sts = telemetry.session_start_timestamp
    assert sid
    assert sts

    # retrieve from the db if process restarted
    telemetry_2 = Telemetry()
    await telemetry_2.start(loops=1)
    assert telemetry_2.session_id == sid
    assert telemetry_2.session_start_timestamp == sts


async def test_errors_shutdown_service(error_sens_o_matic_mock, caplog):
    # When telemetry encounters an error on any loop the service is stopped
    telemetry = Telemetry()

    await telemetry.start(loops=5)

    # The service should only be hit once
    assert error_sens_o_matic_mock.called
    assert error_sens_o_matic_mock.call_count == 1

    # Filter for telemetry error logs
    records = [
        record
        for record in caplog.records
        if record.name == "syntask.server.services.telemetry"
        and record.levelname == "ERROR"
    ]

    assert len(records) == 1, "An error level log should be emitted"
    assert (
        "Failed to send telemetry" in records[0].message
    ), "Should inform the user of the failure"

    assert (
        "Server error '500 Internal Server Error' for url" in records[0].message
    ), "Should include a short version of the exception"
