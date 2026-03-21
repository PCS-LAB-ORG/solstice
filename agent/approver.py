from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich import box

console = Console()

PRIORITY_COLOR = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}
CATEGORY_COLOR = {
    "ESCALATION": "bold red",
    "CUSTOMER_OUTREACH": "orange1",
    "BLOCKER_REVIEW": "yellow",
    "STATUS_UPDATE": "cyan",
    "PS_ENGAGEMENT": "blue",
    "EXPIRY_RISK": "magenta",
    "UNCLASSIFIED": "white",
}


def _display_task(task: dict, idx: int, total: int) -> None:
    color = PRIORITY_COLOR.get(task["priority"], "white")
    cat_color = CATEGORY_COLOR.get(task["category"], "white")
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Field", style="dim", width=20)
    table.add_column("Value")
    table.add_row("Account", f"[bold]{task['customer_name']}[/bold] ({task['account_id']})")
    table.add_row("Region / CSE", f"{task['region']} / {task['cse']}")
    table.add_row("Category", f"[{cat_color}]{task['category']}[/{cat_color}]")
    table.add_row("Priority", f"[{color}]{task['priority']}[/{color}]")
    table.add_row("Change", f"{task.get('old_value', '—')} → {task.get('new_value', '—')}")
    table.add_row("Suggested action", f"[italic]{task['suggested_action']}[/italic]")
    console.print(Panel(table, title=f"[bold]Task {idx}/{total}[/bold]", border_style=color))


def run_approval(tasks: list) -> tuple:
    """Interactive terminal approval. Returns (approved_tasks, skipped_count)."""
    if not tasks:
        return [], 0

    approved = []
    skipped = 0
    total = len(tasks)

    for i, task in enumerate(tasks, start=1):
        _display_task(task, i, total)
        choice = Prompt.ask(
            "[bold][A][/bold]pprove  [bold][R][/bold]eject  [bold][E][/bold]dit  [bold][S][/bold]kip all",
            default="a",
        ).strip().lower()

        if choice == "a":
            approved.append(task)
        elif choice == "r":
            console.print("[dim]Rejected.[/dim]")
        elif choice == "e":
            new_action = Prompt.ask("New suggested action")
            approved.append({**task, "suggested_action": new_action})
        elif choice == "s":
            skipped = total - i + 1  # current task + all remaining
            console.print(f"[dim]Skipping {skipped} remaining task(s).[/dim]")
            break

    console.print(f"\n[green]Approved: {len(approved)}[/green]  [dim]Skipped: {skipped}[/dim]")
    return approved, skipped
