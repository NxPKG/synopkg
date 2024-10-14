"""
Command line interface for working with Syntask
"""

import logging
import os
import shlex
import socket
import sys
import textwrap

import anyio
import anyio.abc
import typer

import syntask
from syntask.cli._prompts import prompt
from syntask.cli._types import SettingsOption, SyntaskTyper
from syntask.cli._utilities import exit_with_error, exit_with_success
from syntask.cli.cloud import prompt_select_from_list
from syntask.cli.root import app, is_interactive
from syntask.logging import get_logger
from syntask.settings import (
    SYNTASK_API_SERVICES_LATE_RUNS_ENABLED,
    SYNTASK_API_SERVICES_SCHEDULER_ENABLED,
    SYNTASK_API_URL,
    SYNTASK_HOME,
    SYNTASK_LOGGING_SERVER_LEVEL,
    SYNTASK_SERVER_ANALYTICS_ENABLED,
    SYNTASK_SERVER_API_HOST,
    SYNTASK_SERVER_API_KEEPALIVE_TIMEOUT,
    SYNTASK_SERVER_API_PORT,
    SYNTASK_UI_ENABLED,
    Profile,
    load_current_profile,
    load_profiles,
    save_profiles,
    update_current_profile,
)
from syntask.utilities.asyncutils import run_sync_in_worker_thread
from syntask.utilities.processutils import (
    consume_process_output,
    setup_signal_handlers_server,
)

server_app = SyntaskTyper(
    name="server",
    help="Start a Syntask server instance and interact with the database",
)
database_app = SyntaskTyper(name="database", help="Interact with the database.")
server_app.add_typer(database_app)
app.add_typer(server_app)

logger = get_logger(__name__)

PID_FILE = "server.pid"


def generate_welcome_blurb(base_url, ui_enabled: bool):
    blurb = textwrap.dedent(
        r"""
         ___ ___ ___ ___ ___ ___ _____ 
        | _ \ _ \ __| __| __/ __|_   _| 
        |  _/   / _|| _|| _| (__  | |  
        |_| |_|_\___|_| |___\___| |_|  

        Configure Syntask to communicate with the server with:

            syntask config set SYNTASK_API_URL={api_url}

        View the API reference documentation at {docs_url}
        """
    ).format(api_url=base_url + "/api", docs_url=base_url + "/docs")

    visit_dashboard = textwrap.dedent(
        f"""
        Check out the dashboard at {base_url}
        """
    )

    dashboard_not_built = textwrap.dedent(
        """
        The dashboard is not built. It looks like you're on a development version.
        See `syntask dev` for development commands.
        """
    )

    dashboard_disabled = textwrap.dedent(
        """
        The dashboard is disabled. Set `SYNTASK_UI_ENABLED=1` to re-enable it.
        """
    )

    if not os.path.exists(syntask.__ui_static_path__):
        blurb += dashboard_not_built
    elif not ui_enabled:
        blurb += dashboard_disabled
    else:
        blurb += visit_dashboard

    return blurb


def prestart_check(base_url: str):
    """
    Check if `SYNTASK_API_URL` is set in the current profile. If not, prompt the user to set it.

    Args:
        base_url: The base URL the server will be running on
    """
    api_url = f"{base_url}/api"
    current_profile = load_current_profile()
    profiles = load_profiles()
    if current_profile and SYNTASK_API_URL not in current_profile.settings:
        profiles_with_matching_url = [
            name
            for name, profile in profiles.items()
            if profile.settings.get(SYNTASK_API_URL) == api_url
        ]
        if len(profiles_with_matching_url) == 1:
            profiles.set_active(profiles_with_matching_url[0])
            save_profiles(profiles)
            app.console.print(
                f"Switched to profile {profiles_with_matching_url[0]!r}",
                style="green",
            )
            return
        elif len(profiles_with_matching_url) > 1:
            app.console.print(
                "Your current profile doesn't have `SYNTASK_API_URL` set to the address"
                " of the server that's running. Some of your other profiles do."
            )
            selected_profile = prompt_select_from_list(
                app.console,
                "Which profile would you like to switch to?",
                sorted(
                    [profile for profile in profiles_with_matching_url],
                ),
            )
            profiles.set_active(selected_profile)
            save_profiles(profiles)
            app.console.print(
                f"Switched to profile {selected_profile!r}", style="green"
            )
            return

        app.console.print(
            "The `SYNTASK_API_URL` setting for your current profile doesn't match the"
            " address of the server that's running. You need to set it to communicate"
            " with the server.",
            style="yellow",
        )

        choice = prompt_select_from_list(
            app.console,
            "How would you like to proceed?",
            [
                (
                    "create",
                    "Create a new profile with `SYNTASK_API_URL` set and switch to it",
                ),
                (
                    "set",
                    f"Set `SYNTASK_API_URL` in the current profile: {current_profile.name!r}",
                ),
            ],
        )

        if choice == "create":
            while True:
                profile_name = prompt("Enter a new profile name")
                if profile_name in profiles:
                    app.console.print(
                        f"Profile {profile_name!r} already exists. Please choose a different name.",
                        style="red",
                    )
                else:
                    break

            profiles.add_profile(
                Profile(
                    name=profile_name, settings={SYNTASK_API_URL: f"{base_url}/api"}
                )
            )
            profiles.set_active(profile_name)
            save_profiles(profiles)

            app.console.print(
                f"Switched to new profile {profile_name!r}", style="green"
            )
        elif choice == "set":
            api_url = prompt(
                "Enter the `SYNTASK_API_URL` value", default="http://127.0.0.1:4200/api"
            )
            update_current_profile({SYNTASK_API_URL: api_url})
            app.console.print(
                f"Set `SYNTASK_API_URL` to {api_url!r} in the current profile {current_profile.name!r}",
                style="green",
            )


@server_app.command()
async def start(
    host: str = SettingsOption(SYNTASK_SERVER_API_HOST),
    port: int = SettingsOption(SYNTASK_SERVER_API_PORT),
    keep_alive_timeout: int = SettingsOption(SYNTASK_SERVER_API_KEEPALIVE_TIMEOUT),
    log_level: str = SettingsOption(SYNTASK_LOGGING_SERVER_LEVEL),
    scheduler: bool = SettingsOption(SYNTASK_API_SERVICES_SCHEDULER_ENABLED),
    analytics: bool = SettingsOption(
        SYNTASK_SERVER_ANALYTICS_ENABLED, "--analytics-on/--analytics-off"
    ),
    late_runs: bool = SettingsOption(SYNTASK_API_SERVICES_LATE_RUNS_ENABLED),
    ui: bool = SettingsOption(SYNTASK_UI_ENABLED),
    background: bool = typer.Option(
        False, "--background", "-b", help="Run the server in the background"
    ),
):
    """
    Start a Syntask server instance
    """
    base_url = f"http://{host}:{port}"
    if is_interactive():
        try:
            prestart_check(base_url)
        except Exception:
            pass

    server_env = os.environ.copy()
    server_env["SYNTASK_API_SERVICES_SCHEDULER_ENABLED"] = str(scheduler)
    server_env["SYNTASK_SERVER_ANALYTICS_ENABLED"] = str(analytics)
    server_env["SYNTASK_API_SERVICES_LATE_RUNS_ENABLED"] = str(late_runs)
    server_env["SYNTASK_API_SERVICES_UI"] = str(ui)
    server_env["SYNTASK_UI_ENABLED"] = str(ui)
    server_env["SYNTASK_LOGGING_SERVER_LEVEL"] = log_level

    pid_file = anyio.Path(SYNTASK_HOME.value() / PID_FILE)
    # check if port is already in use
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
    except socket.error:
        if await pid_file.exists():
            exit_with_error(
                f"A background server process is already running on port {port}. "
                "Run `syntask server stop` to stop it or specify a different port "
                "with the `--port` flag."
            )
        exit_with_error(
            f"Port {port} is already in use. Please specify a different port with the "
            "`--port` flag."
        )

    # check if server is already running in the background
    if background:
        try:
            await pid_file.touch(mode=0o600, exist_ok=False)
        except FileExistsError:
            exit_with_error(
                "A server is already running in the background. To stop it,"
                " run `syntask server stop`."
            )

    app.console.print(generate_welcome_blurb(base_url, ui_enabled=ui))
    app.console.print("\n")

    try:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "--app-dir",
            str(syntask.__module_path__.parent),
            "--factory",
            "syntask.server.api.server:create_app",
            "--host",
            str(host),
            "--port",
            str(port),
            "--timeout-keep-alive",
            str(keep_alive_timeout),
        ]
        logger.debug("Opening server process with command: %s", shlex.join(command))
        process = await anyio.open_process(
            command=command,
            env=server_env,
        )

        process_id = process.pid
        if background:
            await pid_file.write_text(str(process_id))

            app.console.print(
                "The Syntask server is running in the background. Run `syntask"
                " server stop` to stop it."
            )
            return

        async with process:
            # Explicitly handle the interrupt signal here, as it will allow us to
            # cleanly stop the uvicorn server. Failing to do that may cause a
            # large amount of anyio error traces on the terminal, because the
            # SIGINT is handled by Typer/Click in this process (the parent process)
            # and will start shutting down subprocesses:
            # https://github.com/SynoPKG/server/issues/2475

            setup_signal_handlers_server(
                process_id, "the Syntask server", app.console.print
            )

            await consume_process_output(process, sys.stdout, sys.stderr)

    except anyio.EndOfStream:
        logging.error("Subprocess stream ended unexpectedly")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")

    app.console.print("Server stopped!")


@server_app.command()
async def stop():
    """Stop a Syntask server instance running in the background"""
    pid_file = anyio.Path(SYNTASK_HOME.value() / PID_FILE)
    if not await pid_file.exists():
        exit_with_success("No server running in the background.")
    pid = int(await pid_file.read_text())
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        exit_with_success(
            "The server process is not running. Cleaning up stale PID file."
        )
    finally:
        # The file probably exists, but use `missing_ok` to avoid an
        # error if the file was deleted by another actor
        await pid_file.unlink(missing_ok=True)
    app.console.print("Server stopped!")


@database_app.command()
async def reset(yes: bool = typer.Option(False, "--yes", "-y")):
    """Drop and recreate all Syntask database tables"""
    from syntask.server.database.dependencies import provide_database_interface

    db = provide_database_interface()
    engine = await db.engine()
    if not yes:
        confirm = typer.confirm(
            "Are you sure you want to reset the Syntask database located "
            f'at "{engine.url!r}"? This will drop and recreate all tables.'
        )
        if not confirm:
            exit_with_error("Database reset aborted")
    app.console.print("Downgrading database...")
    await db.drop_db()
    app.console.print("Upgrading database...")
    await db.create_db()
    exit_with_success(f'Syntask database "{engine.url!r}" reset!')


@database_app.command()
async def upgrade(
    yes: bool = typer.Option(False, "--yes", "-y"),
    revision: str = typer.Option(
        "head",
        "-r",
        help=(
            "The revision to pass to `alembic upgrade`. If not provided, runs all"
            " migrations."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        help=(
            "Flag to show what migrations would be made without applying them. Will"
            " emit sql statements to stdout."
        ),
    ),
):
    """Upgrade the Syntask database"""
    from syntask.server.database.alembic_commands import alembic_upgrade
    from syntask.server.database.dependencies import provide_database_interface

    db = provide_database_interface()
    engine = await db.engine()

    if not yes:
        confirm = typer.confirm(
            f"Are you sure you want to upgrade the Syntask database at {engine.url!r}?"
        )
        if not confirm:
            exit_with_error("Database upgrade aborted!")

    app.console.print("Running upgrade migrations ...")
    await run_sync_in_worker_thread(alembic_upgrade, revision=revision, dry_run=dry_run)
    app.console.print("Migrations succeeded!")
    exit_with_success(f"Syntask database at {engine.url!r} upgraded!")


@database_app.command()
async def downgrade(
    yes: bool = typer.Option(False, "--yes", "-y"),
    revision: str = typer.Option(
        "-1",
        "-r",
        help=(
            "The revision to pass to `alembic downgrade`. If not provided, "
            "downgrades to the most recent revision. Use 'base' to run all "
            "migrations."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        help=(
            "Flag to show what migrations would be made without applying them. Will"
            " emit sql statements to stdout."
        ),
    ),
):
    """Downgrade the Syntask database"""
    from syntask.server.database.alembic_commands import alembic_downgrade
    from syntask.server.database.dependencies import provide_database_interface

    db = provide_database_interface()

    engine = await db.engine()

    if not yes:
        confirm = typer.confirm(
            "Are you sure you want to downgrade the Syntask "
            f"database at {engine.url!r}?"
        )
        if not confirm:
            exit_with_error("Database downgrade aborted!")

    app.console.print("Running downgrade migrations ...")
    await run_sync_in_worker_thread(
        alembic_downgrade, revision=revision, dry_run=dry_run
    )
    app.console.print("Migrations succeeded!")
    exit_with_success(f"Syntask database at {engine.url!r} downgraded!")


@database_app.command()
async def revision(
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="A message to describe the migration.",
    ),
    autogenerate: bool = False,
):
    """Create a new migration for the Syntask database"""
    from syntask.server.database.alembic_commands import alembic_revision

    app.console.print("Running migration file creation ...")
    await run_sync_in_worker_thread(
        alembic_revision,
        message=message,
        autogenerate=autogenerate,
    )
    exit_with_success("Creating new migration file succeeded!")


@database_app.command()
async def stamp(revision: str):
    """Stamp the revision table with the given revision; don't run any migrations"""
    from syntask.server.database.alembic_commands import alembic_stamp

    app.console.print("Stamping database with revision ...")
    await run_sync_in_worker_thread(alembic_stamp, revision=revision)
    exit_with_success("Stamping database with revision succeeded!")
