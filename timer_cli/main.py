"""
TODO:
    - look into https://github.com/click-contrib/click-help-colors
"""

import datetime
import json
import sys
from typing import Optional
import urllib.parse
import uuid

import click
import requests

from timer_cli.auth import get_access_token


# how long to wait before giving up on requests to the API
TIMEOUT = 10


def show_usage(cmd: click.Command):
    """
    Show the relevant usage and exit.

    The actual usage message is accurate for incomplete commands, e.g.
    """
    ctx = click.get_current_context()
    formatter = ctx.make_formatter()
    cmd.format_help_text(ctx, formatter)
    cmd.format_options(ctx, formatter)
    cmd.format_epilog(ctx, formatter)
    click.echo(formatter.getvalue().rstrip("\n"))
    ctx.exit()
    sys.exit(2)


def show_response(response: requests.Response):
    if response.status_code >= 400:
        click.echo(f"got response code {response.status_code}", err=True)
    click.echo(json.dumps(response.json()))


def handle_requests_exception(e: Exception):
    click.echo(f"error in request: {e}", err=True)
    sys.exit(1)


class Command(click.Command):
    """
    Subclass click.Command to show help message if a command is missing arguments.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for some reason this does nothing---would like to fix
        #     self.context_settings.update({
        #         "max_content_width": 120,
        #     })

    def make_context(self, *args, **kwargs):
        try:
            return super().make_context(*args, **kwargs)
        except click.MissingParameter as e:
            e.cmd = None
            e.show()
            click.echo()
            show_usage(self)
        except (
            click.BadArgumentUsage,
            click.BadOptionUsage,
            click.BadParameter,
        ) as e:
            e.cmd = None
            e.show()
            click.echo()
            show_usage(self)
            sys.exit(e.exit_code)


class URL(click.ParamType):
    """Click param type for a URL."""

    name = "url"

    def convert(self, value, param, ctx):
        if not isinstance(value, tuple):
            value = urllib.parse.urlparse(value)
            if not value.netloc:
                self.fail("incomplete URL")
            if value.scheme not in ("http", "https"):
                self.fail(
                    f"invalid URL scheme ({value.scheme}). Only HTTP URLs are allowed",
                    param,
                    ctx,
                )
        return value


def get_headers(token_store: Optional[str] = None) -> dict:
    """
    Assemble any needed headers that should go in all requests to the timer API, such
    as the access token.
    """
    access_token = get_access_token(token_store=token_store)
    return {"Authorization": f"Bearer {access_token}"}


cli = click.Group()


@cli.group()
def job():
    pass


@job.command(cls=Command)
@click.option(
    "--name",
    required=True,
    type=str,
    help="name to identify this job (not necessarily unique)",
)
@click.option(
    "--start",
    required=False,
    type=click.DateTime(),
    help=(
        "start time for the job (defaults to current time)"
    ),
)
@click.option(
    "--interval",
    required=True,
    type=int,
    help="interval in seconds at which the job should run",
)
@click.option(
    "--action-url",
    required=True,
    type=URL(),
    help=(
        "The URL for the action to run, e.g. "
        "https://actions.automate.globus.org/transfer/transfer/run"
    ),
)
@click.option(
    "--action-body",
    required=True,
    type=str,
    help="request JSON body to send to the action provider on job execution",
)
def submit(
    name: str,
    start: Optional[click.DateTime],
    interval: int,
    action_url: urllib.parse.ParseResult,
    action_body: str,
):
    """
    Submit a new job.
    """
    try:
        callback_body = action_body.strip("'").strip('"')
        callback_body = json.loads(action_body)
    except (TypeError, ValueError) as e:
        raise click.BadOptionUsage(
            "action-body",
            f"--action-body must parse into valid JSON; got error: {e}",
        )
    start = start or datetime.datetime.now()
    callback_url: str = action_url.geturl()
    req_json = {
        "name": name,
        "start": start.isoformat(),
        "interval": interval,
        "callback_url": callback_url,
        "callback_body": callback_body,
    }
    headers = get_headers()
    try:
        response = requests.post(
            "https://sandbox.timer.automate.globus.org/jobs/",
            json=req_json,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return
    show_response(response)


@job.command(cls=Command)
def list():
    """
    List submitted jobs.
    """
    headers = get_headers()
    try:
        response = requests.get(
            f"https://sandbox.timer.automate.globus.org/jobs/",
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return
    show_response(response)


@job.command(cls=Command)
@click.argument(
    "job_id",
    type=uuid.UUID,
)
def status(
    job_id: uuid.UUID,
):
    """
    Return the status of the job with the given ID.
    """
    headers = get_headers()
    try:
        response = requests.get(
            f"https://sandbox.timer.automate.globus.org/jobs/{job_id}",
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return
    show_response(response)


def main():
    cli()


if __name__ == '__main__':
    cli()
