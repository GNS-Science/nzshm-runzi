"""The main runzi CLI script"""

import inversion_post_process_cli
import reports_cli
import rupture_sets_cli
import typer
import utils_cli

app = typer.Typer(help="The NZ NSHM runzi CLI.", no_args_is_help=True)
app.add_typer(inversion_post_process_cli.app, name="ipp", help="inversion post processing", no_args_is_help=True)
app.add_typer(rupture_sets_cli.app, name="rupset", help="create rupture sets", no_args_is_help=True)
app.add_typer(reports_cli.app, name="reports", help="create inversion and rupture set reports", no_args_is_help=True)
app.add_typer(utils_cli.app, name="utils", help="utilities", no_args_is_help=True)

if __name__ == "__main__":
    app()
