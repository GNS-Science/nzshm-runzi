import inversion_post_process_cli
import reports_cli
import rupture_sets_cli
import typer

app = typer.Typer(help="The NZ NSHM runzi CLI.")
app.add_typer(inversion_post_process_cli.app, name="ipp", help="post process inversions")
app.add_typer(rupture_sets_cli.app, name="rupset", help="create rupture sets")
app.add_typer(reports_cli.app, name="reports", help="create inversion and rupture set reports")

if __name__ == "__main__":
    app()
