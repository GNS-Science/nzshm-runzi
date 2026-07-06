"""The `runzi batch` CLI: read-only inspection of a general task's AWS Batch jobs (issues #326, #337).

Federated Cognito users have no AWS console access, so this surfaces the job state and logs they
otherwise couldn't see. It is deliberately read-only — it inspects jobs and downloads their logs but
never mutates them (no terminate in this version).
"""

import datetime as dt
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table

from runzi.aws.batch_query import (
    JobNotFound,
    LogStreamNotAvailable,
    job_duration,
    job_log_events,
    jobs_for_general_task,
    swept_arg_keys,
    task_args_by_job_id,
)

app = typer.Typer()
console = Console()

# Batch statuses we colour; everything else (SUBMITTED/PENDING/RUNNABLE/STARTING — i.e. still queued)
# renders dim.
_STATUS_STYLE = {'SUCCEEDED': 'green', 'FAILED': 'red', 'RUNNING': 'yellow'}


def _created(summary: dict) -> str:
    ms = summary.get('createdAt')
    if not ms:
        return '-'
    return dt.datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M:%S')


def _exit_on_access_denied(exc: ClientError, permission: str) -> None:
    """Print a friendly message and exit(1) if `exc` is an access-denied error; otherwise return."""
    code = exc.response.get('Error', {}).get('Code', '')
    if code in ('AccessDenied', 'AccessDeniedException'):
        console.print(
            f"[red]Access denied calling {permission}.[/red] Your access tier lacks AWS Batch "
            "read permissions; log in at the runzi-batch tier with `toshi-auth login`."
        )
        raise typer.Exit(code=1) from None


@app.command()
def status(
    general_task_id: Annotated[str, typer.Argument(help="the GENERAL_TASK_ID printed at submission")],
):
    """Show the AWS Batch jobs for a general task: id, status, duration, created time, swept args.

    A column is added per swept argument (the args whose values differ across this task's jobs),
    read from each job's own shipped config. Caveats: AWS Batch keeps terminal (SUCCEEDED/FAILED)
    jobs for only ~24h, and only jobs submitted after this feature shipped carry the discoverable job
    name — older jobs won't appear. Because swept columns are inferred from what varies among the
    jobs still visible, a swept arg that is constant across the survivors won't get a column.
    """
    try:
        jobs = jobs_for_general_task(general_task_id)
    except ClientError as exc:
        _exit_on_access_denied(exc, 'batch:ListJobs')
        raise

    if not jobs:
        console.print(
            f"[yellow]Found no Batch jobs for general task {general_task_id}.[/yellow] Terminal jobs "
            "age out of AWS Batch after ~24h, and only jobs submitted after this feature shipped are "
            "discoverable."
        )
        return

    try:
        task_args_by_job = task_args_by_job_id([job['jobId'] for job in jobs])
    except ClientError as exc:
        _exit_on_access_denied(exc, 'batch:DescribeJobs')
        raise

    swept_keys = swept_arg_keys(task_args_by_job)

    table = Table(title=f"Batch jobs for {general_task_id}")
    for column in ("Job ID", "Status", "Duration", "Created", *swept_keys):
        table.add_column(column)
    for job in jobs:
        job_status = job.get('status', 'UNKNOWN')
        style = _STATUS_STYLE.get(job_status, 'dim')
        args = task_args_by_job.get(job.get('jobId', ''), {})
        swept_cells = [str(args.get(key, '')) for key in swept_keys]
        table.add_row(
            job.get('jobId', '-'),
            f"[{style}]{job_status}[/]",
            job_duration(job),
            _created(job),
            *swept_cells,
        )
    console.print(table)

    counts = Counter(job.get('status', 'UNKNOWN') for job in jobs)
    breakdown = "  ".join(f"{name}: {n}" for name, n in sorted(counts.items()))
    console.print(f"[bold]{len(jobs)} job(s)[/bold]  {breakdown}")


@app.command()
def log(
    job_id: Annotated[str, typer.Argument(help="the Job ID printed by `runzi batch status`")],
):
    """Fetch a single Batch job's CloudWatch log and write it to ``<JOB_ID>.log`` in the current dir.

    Find the Job ID with `runzi batch status`. AWS Batch keeps terminal jobs (and their logs) for
    only ~24h, so a very old job may no longer have retrievable logs.
    """
    try:
        lines = list(job_log_events(job_id))
    except JobNotFound:
        console.print(
            f"[red]No Batch job found with id {job_id}.[/red] Check the id from `runzi batch "
            "status`; terminal jobs age out of AWS Batch after ~24h."
        )
        raise typer.Exit(code=1) from None
    except LogStreamNotAvailable:
        console.print(
            f"[yellow]Job {job_id} has no log stream yet.[/yellow] It has not started running, so "
            "there are no logs to fetch."
        )
        raise typer.Exit(code=0) from None
    except ClientError as exc:
        _exit_on_access_denied(exc, 'logs:GetLogEvents')
        raise

    path = Path(f"{job_id}.log")
    path.write_text(''.join(f'{line}\n' for line in lines))
    console.print(f"[green]Wrote {len(lines)} line(s) to {path}.[/green]")


if __name__ == "__main__":
    app()
