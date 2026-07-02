"""The `runzi batch` CLI: read-only inspection of a general task's AWS Batch jobs (issue #326).

Federated Cognito users have no AWS console access, so this surfaces the job state they otherwise
couldn't see. It is deliberately read-only (no terminate / log-fetching in this version).
"""

import datetime as dt
from collections import Counter
from typing import Annotated

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table

from runzi.aws.batch_query import job_duration, jobs_for_general_task

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


@app.command()
def status(
    general_task_id: Annotated[str, typer.Argument(help="the GENERAL_TASK_ID printed at submission")],
):
    """Show the AWS Batch jobs for a general task: name, id, status, duration, created time.

    Caveats: AWS Batch keeps terminal (SUCCEEDED/FAILED) jobs for only ~24h, and only jobs submitted
    after this feature shipped carry the discoverable job name — older jobs won't appear.
    """
    try:
        jobs = jobs_for_general_task(general_task_id)
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', '')
        if code in ('AccessDenied', 'AccessDeniedException'):
            console.print(
                "[red]Access denied calling batch:ListJobs.[/red] Your access tier lacks AWS Batch "
                "read permissions; log in at the runzi-batch tier with `toshi-auth login`."
            )
            raise typer.Exit(code=1) from None
        raise

    if not jobs:
        console.print(
            f"[yellow]Found no Batch jobs for general task {general_task_id}.[/yellow] Terminal jobs "
            "age out of AWS Batch after ~24h, and only jobs submitted after this feature shipped are "
            "discoverable."
        )
        return

    table = Table(title=f"Batch jobs for {general_task_id}")
    for column in ("Job Name", "Job ID", "Status", "Duration", "Created"):
        table.add_column(column)
    for job in jobs:
        job_status = job.get('status', 'UNKNOWN')
        style = _STATUS_STYLE.get(job_status, 'dim')
        table.add_row(
            job.get('jobName', '-'),
            job.get('jobId', '-'),
            f"[{style}]{job_status}[/]",
            job_duration(job),
            _created(job),
        )
    console.print(table)

    counts = Counter(job.get('status', 'UNKNOWN') for job in jobs)
    breakdown = "  ".join(f"{name}: {n}" for name, n in sorted(counts.items()))
    console.print(f"[bold]{len(jobs)} job(s)[/bold]  {breakdown}")


if __name__ == "__main__":
    app()
