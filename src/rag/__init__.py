import typer

app = typer.Typer()


@app.command()
def hello(name: str = "world!"):
    print(f"Hello {name}")
