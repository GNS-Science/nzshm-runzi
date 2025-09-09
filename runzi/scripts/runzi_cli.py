import inversion_post_process_cli
import rupture_sets_cli
import typer

app = typer.Typer(help="The NZ NSHM runzi CLI.")
app.add_typer(inversion_post_process_cli.app, name="ipp", help="post process inversions")
app.add_typer(rupture_sets_cli.app, name="rupset", help="create rupture sets")

if __name__ == "__main__":
    app()
