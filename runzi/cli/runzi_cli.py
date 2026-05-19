"""The main runzi CLI script"""

from typing import Annotated

import click
import typer
from typer.core import TyperGroup

from runzi.automation import local_config
from runzi.automation.local_config import ClusterModeEnum
from runzi.cli import (
    docker_wrapper,
    hazard_cli,
    inversion_cli,
    inversion_post_process_cli,
    reports_cli,
    rupture_sets_cli,
    utils_cli,
)

# ── Arg capture helpers ───────────────────────────────────────────────────────

_DOCKER_BOOL_FLAGS: frozenset[str] = frozenset(
    ['--docker', '--docker-dev', '--docker-shell', '--docker-dry-run']
)
_DOCKER_VALUE_FLAGS: frozenset[str] = frozenset(['--docker-image'])


def _strip_docker_flags(args: list[str]) -> list[str]:
    """Remove --docker-* flags (and their values) from a raw argv list."""
    result: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _DOCKER_BOOL_FLAGS:
            pass  # drop boolean flag
        elif arg in _DOCKER_VALUE_FLAGS:
            i += 2  # drop --flag VALUE pair
            continue
        elif any(arg.startswith(f'{f}=') for f in _DOCKER_VALUE_FLAGS):
            pass  # drop --flag=value form
        else:
            result.append(arg)
        i += 1
    return result


class _ArgsCapturingGroup(TyperGroup):
    """Typer Group subclass that stores the raw pre-parse args in ctx.meta.

    Click's Group.invoke() clears ctx.args and ctx.protected_args before
    invoking the callback, so the callback cannot recover the subcommand name
    and its arguments from those attributes.  Capturing the args here, before
    Click's own processing, is the only reliable interception point.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        ctx.meta['_raw_args'] = list(args)
        return super().parse_args(ctx, args)


# ── Typer app ─────────────────────────────────────────────────────────────────

app = typer.Typer(help="The NZ NSHM runzi CLI.", no_args_is_help=True, cls=_ArgsCapturingGroup)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    cluster_mode: Annotated[
        ClusterModeEnum, typer.Option(help="Execution target: LOCAL machine, HPC CLUSTER, or AWS cloud.")
    ] = local_config.DEFAULT_CLUSTER_MODE,
    docker: Annotated[bool, typer.Option('--docker', help="Run the command inside a local Docker container.")] = False,
    docker_dev: Annotated[
        bool,
        typer.Option(
            '--docker-dev', help="Run in Docker using the dev image with editable host source mount. Implies --docker."
        ),
    ] = False,
    docker_image: Annotated[
        str | None,
        typer.Option('--docker-image', help="Override the Docker image tag or full ECR URI. Implies --docker."),
    ] = None,
    docker_shell: Annotated[
        bool,
        typer.Option(
            '--docker-shell', help="Drop into an interactive bash shell inside the container. Implies --docker."
        ),
    ] = False,
    docker_dry_run: Annotated[
        bool,
        typer.Option(
            '--docker-dry-run', help="Print the docker command that would run, without executing it. Implies --docker."
        ),
    ] = False,
) -> None:
    """The NZ NSHM runzi CLI.

    Prefix any command with --docker to run it inside a local Docker container instead of natively.
    """
    local_config.CLUSTER_MODE = cluster_mode

    if cluster_mode is ClusterModeEnum.AWS:
        if not local_config.API_KEY:
            raise typer.BadParameter(
                'NZSHM22_TOSHI_API_KEY (or AWS Secrets Manager) is required when --cluster-mode is AWS.',
                param_hint="'--cluster-mode'",
            )
        local_config.USE_API = True

    use_docker = docker or docker_dev or docker_shell or docker_dry_run or (docker_image is not None)
    if use_docker:
        raw_args = ctx.meta.get('_raw_args', [])
        inner_args = _strip_docker_flags(raw_args)
        exit_code = docker_wrapper.run_in_docker(
            inner_args,
            dev=docker_dev,
            image=docker_image,
            shell=docker_shell,
            dry_run=docker_dry_run,
        )
        raise typer.Exit(exit_code)

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


app.add_typer(inversion_cli.app, name="inversion", help="inversion", no_args_is_help=True)
app.add_typer(hazard_cli.app, name="hazard", help="hazard calculations", no_args_is_help=True)
app.add_typer(inversion_post_process_cli.app, name="ipp", help="inversion post processing", no_args_is_help=True)
app.add_typer(rupture_sets_cli.app, name="rupset", help="create rupture sets", no_args_is_help=True)
app.add_typer(reports_cli.app, name="reports", help="create inversion and rupture set reports", no_args_is_help=True)
app.add_typer(utils_cli.app, name="utils", help="utilities", no_args_is_help=True)


if __name__ == "__main__":
    app()
