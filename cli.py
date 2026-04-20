#!/usr/bin/env python3
"""
ArchDocAI CLI - Automatic Architecture Documentation
Usage:  python cli.py analyze ./my-project
"""

import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from dotenv import load_dotenv

app = typer.Typer(name="archdoc", help="ArchDocAI - Automatic Architecture Documentation")
console = Console()


@app.command()
def analyze(
    project_path: str = typer.Argument(..., help="Path to the project directory to analyze"),
    project_name: str = typer.Option(None, "--name", "-n", help="Override project name"),
    language: str = typer.Option("pt", "--lang", "-l", help="Output language: pt | en"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    no_diagram: bool = typer.Option(False, "--no-diagram", help="Skip diagram generation"),
    no_docx: bool = typer.Option(False, "--no-docx", help="Skip .docx generation"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF generation"),
    no_md: bool = typer.Option(False, "--no-md", help="Skip Markdown generation"),
    skip_validation: bool = typer.Option(False, "--yes", "-y", help="Skip interactive validation"),
):
    """Analyze a project and generate architecture documentation."""
    load_dotenv()

    # ── Import layers ────────────────────────────────────────────────────────
    from src.ingestion import ProjectContext
    from src.analysis import LLMClient, ArchitectureAnalyzer, DiagramGenerator
    from src.output import DocxGenerator, PdfGenerator, MarkdownGenerator

    path = Path(project_path).resolve()
    if not path.is_dir():
        console.print(f"[red]Error: {path} is not a directory[/red]")
        raise typer.Exit(1)

    # ── Step 1: Scan project ─────────────────────────────────────────────────
    console.print(Panel(f"[bold cyan]ArchDocAI[/bold cyan]\nAnalyzing: [yellow]{path}[/yellow]"))

    with console.status("[bold green]Scanning project files..."):
        ctx = ProjectContext.from_path(str(path), project_name=project_name)

    summary = ctx.summary()
    table = Table(title="Project Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Project", summary["project_name"])
    table.add_row("Files scanned", str(summary["total_files"]))
    table.add_row("Total size", f"{summary['total_size_kb']} KB")
    table.add_row("Languages", ", ".join(f"{k} ({v})" for k, v in summary["languages"].items()))
    console.print(table)

    # ── Step 2: LLM Analysis ─────────────────────────────────────────────────
    with console.status("[bold green]Connecting to LLM..."):
        try:
            client = LLMClient.from_env()
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    provider_label = os.getenv("LLM_PROVIDER", "openai").upper()
    model_label = os.getenv("LLM_MODEL", "gpt-4o")
    console.print(f"[green]Using:[/green] {provider_label} / {model_label}")

    with console.status("[bold green]Analyzing architecture with LLM (this may take ~30s)..."):
        analyzer = ArchitectureAnalyzer(client=client, language=language)
        result = analyzer.analyze(ctx)

    console.print(f"\n[bold green]Architecture identified:[/bold green] {len(result.layers)} layers")
    for layer in result.layers:
        console.print(f"  [cyan]•[/cyan] {layer['name']} ({len(layer.get('components', []))} components)")

    # ── Step 3: Interactive Validation ───────────────────────────────────────
    if not skip_validation and result.validation_questions:
        console.print("\n[bold yellow]Validation Questions[/bold yellow]")
        console.print("The AI has some questions to confirm the architecture:")
        answers: dict[str, str] = {}

        for i, question in enumerate(result.validation_questions, 1):
            console.print(f"\n[cyan]{i}.[/cyan] {question}")
            answer = Prompt.ask("Your answer (or Enter to skip)")
            if answer.strip():
                answers[question] = answer

        if answers:
            with console.status("[bold green]Updating analysis with your corrections..."):
                result = analyzer.validate_with_user(result, answers)
            console.print("[green]Analysis updated with your input.[/green]")

    # ── Step 4: Diagram ──────────────────────────────────────────────────────
    diagram_path = None
    interactive_diagram_path = None
    if not no_diagram:
        with console.status("[bold green]Generating architecture diagram..."):
            gen = DiagramGenerator(output_dir=output_dir)
            diagram_path = gen.generate_png(result)
        console.print(f"[green]Diagram saved:[/green] {diagram_path}")

        with console.status("[bold green]Generating interactive node-graph PNG..."):
            interactive_diagram_path = gen.generate_interactive_png(result)
        console.print(f"[green]Interactive node-graph saved:[/green] {interactive_diagram_path}")

        mermaid = gen.generate_mermaid(result)
        mmd_path = Path(output_dir) / f"{result.project_name.replace(' ', '_')}_diagram.mmd"
        mmd_path.parent.mkdir(parents=True, exist_ok=True)
        mmd_path.write_text(mermaid)
        console.print(f"[green]Mermaid markup:[/green] {mmd_path}")

    # ── Step 5: Documents ────────────────────────────────────────────────────
    if not no_docx:
        with console.status("[bold green]Generating .docx..."):
            docx_gen = DocxGenerator(output_dir=output_dir, language=language)
            docx_path = docx_gen.generate(result, diagram_path=diagram_path,
                                          interactive_diagram_path=interactive_diagram_path)
        console.print(f"[green].docx saved:[/green] {docx_path}")

    if not no_pdf:
        with console.status("[bold green]Generating PDF..."):
            pdf_gen = PdfGenerator(output_dir=output_dir, language=language)
            pdf_path = pdf_gen.generate(result, diagram_path=diagram_path,
                                        interactive_diagram_path=interactive_diagram_path)
        console.print(f"[green]PDF saved:[/green] {pdf_path}")

    if not no_md:
        with console.status("[bold green]Generating Markdown..."):
            md_gen = MarkdownGenerator(output_dir=output_dir, language=language)
            md_mermaid = gen.generate_mermaid(result) if not no_diagram else None
            md_path = md_gen.generate(result, mermaid=md_mermaid)
        console.print(f"[green]Markdown saved:[/green] {md_path}")

    console.print(Panel("[bold green]Done! Documentation generated successfully.[/bold green]"))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8080, help="Port to listen on"),
):
    """Start the ArchDocAI web interface."""
    import uvicorn
    from web.app import create_app
    uvicorn.run(create_app(), host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
