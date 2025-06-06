#!ENTER_SHABANG_PATH
import argparse
import requests
import sys
import re
import time
from urllib.parse import urlparse
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich import box
from rich.spinner import Spinner
from rich.live import Live
from datetime import datetime

try:
    import pyperclip
except ImportError:
    pyperclip = None

console = Console()

API_KEY = "ENTER_PERPLEXITY_API_KEY"
API_URL = "https://api.perplexity.ai/chat/completions"
BUDGET = 100.0

def print_argument_structure():
    """Display the structure of available command-line arguments."""
    table = Table(title="[bold]Command-Line Arguments[/bold]", box=box.ROUNDED, border_style="blue", show_edge=True, expand=True)
    table.add_column("Argument", style="cyan", justify="left")
    table.add_column("Type", style="green", justify="left")
    table.add_column("Description", style="white", overflow="fold")
    table.add_column("Default", style="magenta", justify="left")

    table.add_row(
        "prompt",
        "String (multiple)",
        "Your query or question for the Perplexity API (wrap in quotes for multi-word input)",
        "None (optional if --file is provided)"
    )
    table.add_row(
        "--model",
        "String",
        "The Perplexity model to use for the query or analysis",
        "sonar-pro"
    )
    table.add_row(
        "--verbose",
        "Flag (boolean)",
        "Request a detailed, verbose response with explanations, examples, and context",
        "False"
    )
    table.add_row(
        "--copy-code",
        "Flag (boolean)",
        "Copy code blocks from the response to the clipboard (requires pyperclip)",
        "False"
    )
    table.add_row(
        "--file",
        "String",
        "Path to a Python file to analyze for bugs and optimization suggestions",
        "None (optional)"
    )

    console.print()
    console.print(Panel(
        table,
        title="[bold magenta]Usage Guide[/bold magenta]",
        border_style="medium_purple",
        box=box.ROUNDED,
        width=console.width,
        padding=(1, 2),
        subtitle="[italic gray]Run with a prompt, e.g., 'qp \"latest AI news\"', or a file, e.g., 'qp --file mycode.py'[/italic gray]"
    ))
    console.print()

def is_image(url):
    parsed = urlparse(url)
    path = parsed.path
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
    return any(path.lower().endswith(ext) for ext in image_extensions)

def calculate_cost(usage, model):
    """Calculate cost based on usage and model pricing (Perplexity, June 2025)"""
    # All prices are per 1,000 tokens
    pricing = {
        # Perplexity Sonar models
        "sonar-small-online": {"input": 0.0005, "output": 0.0005},
        "sonar-medium-online": {"input": 0.001, "output": 0.001},
        "sonar-large-online": {"input": 0.003, "output": 0.015},
        "sonar": {"input": 0.001, "output": 0.001},
        "sonar-pro": {"input": 0.003, "output": 0.015},
        # OpenAI GPT-3.5/4
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4": {"input": 0.03, "output": 0.06},
        # Meta Llama 3
        "llama-3-8b-instruct": {"input": 0.0004, "output": 0.0006},
        "llama-3-70b-instruct": {"input": 0.0012, "output": 0.0024},
        # Google Gemini
        "gemini-pro": {"input": 0.00025, "output": 0.0005},
        # Anthropic Claude 3
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    }
    if model not in pricing:
        return 0.0
    input_cost = (usage.get("prompt_tokens", 0) / 1000) * pricing[model]["input"]
    output_cost = (usage.get("completion_tokens", 0) / 1000) * pricing[model]["output"]
    return input_cost + output_cost

class CostTracker:
    def __init__(self, initial_budget=BUDGET, mode=None):
        self.initial_budget = initial_budget
        self.used_cost = 0.0
        self.mode = mode
    
    def add_query_cost(self, cost):
        self.used_cost += cost
    
    def get_remaining_budget(self):
        return self.initial_budget - self.used_cost
    
    def get_info_text(self, model, cost_this_query, now):
        mode = "Verbose" if self.mode else "Concise"
        return (
            f"[bold]Perplexity Query Tool[/bold] | Model: {model} | Mode: {mode}\n"
            f"Query Time: {now} | Cost This Query: ${cost_this_query:.6f} | "
            f"Total Used: ${self.used_cost:.6f} | Remaining: ${self.get_remaining_budget():.6f}"
        )

def read_file_content(file_path):
    """Read the content of a file and return it as a string."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        console.print(f"[red]Error: File '{file_path}' not found.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error reading file '{file_path}': {e}[/red]")
        sys.exit(1)

def analyze_python_file(file_path, model, verbose):
    """Send Python file content to Perplexity API for bug detection and optimization suggestions."""
    file_content = read_file_content(file_path)
    prompt = (
        f"Analyze the following Python code for bugs, potential errors, or inefficiencies. "
        f"If bugs are found, describe them in detail and suggest fixes. "
        f"If no bugs are found, provide detailed suggestions to optimize the code for better performance, readability, and maintainability. "
        f"Here is the code:\n\n```python\n{file_content}\n```"
    )
    reply, search_results, usage, time_taken = call_perplexity_api(prompt, model, verbose)
    return reply, search_results, usage, time_taken

def call_perplexity_api(prompt, model="sonar-pro", verbose=False):
    if verbose:
        system_prompt = """Provide a comprehensive, detailed, and verbose response.
        Include extensive explanations, examples, context, background information, and analysis.
        Break down complex topics into detailed sections with thorough explanations.
        Always cite your sources and provide additional context where relevant."""
        max_tokens = 4000
        search_context = "high"
    else:
        system_prompt = "Be precise and concise. Always cite your sources if available."
        max_tokens = 2000
        search_context = "medium"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "web_search_options": {
            "search_context_size": search_context
        }
    }
    if model == "sonar-deep-research":
        payload["reasoning_effort"] = "high" if verbose else "medium"
    try:
        with Live(Spinner("bouncingBar", text="[bold cyan]Thinking...[/bold cyan]"), refresh_per_second=10, console=console):
            start_time = time.time()
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            end_time = time.time()
            time_taken = end_time - start_time
            response.raise_for_status()
    except requests.exceptions.RequestException as e:
        console.print(Panel(
            f"[bold red]Request failed:[/bold red] {e}\n\n[red]{e.response.text}[/red]",
            title="[bold red]Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
            width=console.width,
            padding=(1, 2)
        ))
        sys.exit(1)
    try:
        data = response.json()
        reply = data["choices"][0]["message"]["content"]
        search_results = data.get("search_results", [])
        usage = data.get("usage", {})
        return reply, search_results, usage, time_taken
    except Exception:
        console.print(Panel(
            f"[bold red]Unexpected API response:[/bold red] {response.text}",
            title="[bold red]Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
            width=console.width,
            padding=(1, 2)
        ))
        sys.exit(1)

def render_search_results(search_results, reply):
    ref_pattern = re.compile(r"\[(\d+)\]")
    refs_in_text = sorted(set(ref_pattern.findall(reply)), key=int)
    if not search_results and not refs_in_text:
        content = Align.center("[bold yellow]No sources cited.[/bold yellow]", vertical="middle")
    else:
        table = Table(box=box.SIMPLE_HEAVY, border_style="cyan", show_edge=True, show_lines=True, expand=True)
        table.add_column("#", style="bold white", width=3, justify="center")
        table.add_column("Title", style="bold green", overflow="fold")
        table.add_column("URL", style="blue", overflow="fold")
        table.add_column("Date", style="magenta", width=12)
        if search_results:
            for idx, src in enumerate(search_results, 1):
                title = src.get("title", "Untitled")
                url = src.get("url", "")
                date = src.get("date", "")
                url_text = f"[link={url}]{url}[/link]" if url else ""
                if url and is_image(url):
                    url_text += " [yellow][Image][/yellow]"
                table.add_row(
                    f"[bold cyan]{idx}[/]",
                    title,
                    url_text,
                    date if date else "-"
                )
        elif refs_in_text:
            for ref in refs_in_text:
                table.add_row(
                    f"[bold cyan]{ref}[/]",
                    "Source cited in response",
                    "",
                    "-"
                )
            table.caption = "[yellow]Note: Specific search results were not provided by the API.[/yellow]"
        content = table
    return Panel(content, title="[bold]Sources[/bold]", border_style="#34b4eb", box=box.ROUNDED, width=console.width, padding=(1, 2))

def main():
    parser = argparse.ArgumentParser(description="Query Perplexity LLM via terminal with citations and code copying.")
    parser.add_argument("prompt", type=str, nargs="*", help="Your prompt/question (wrap in quotes or just type)")
    parser.add_argument("--model", type=str, default="sonar-pro", help="Model to use (default: sonar-pro)")
    parser.add_argument("--verbose", action="store_true", help="Request a verbose response from the model")
    parser.add_argument("--copy-code", action="store_true", help="Copy code blocks to clipboard if present")
    parser.add_argument("--file", type=str, help="Path to a Python file to analyze for bugs and optimization")
    
    args = parser.parse_args()
    cost_tracker = CostTracker(initial_budget=BUDGET, mode=args.verbose)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not args.prompt and not args.file:
        print_argument_structure()
        sys.exit(0)

    if args.file:
        console.print(Panel(
            f"[bold cyan]Analyzing Python file: {args.file}[/bold cyan]",
            title="[bold magenta]File Analysis[/bold magenta]",
            border_style="medium_purple",
            box=box.ROUNDED,
            width=console.width,
            padding=(1, 2)
        ))
        reply, search_results, usage, time_taken = analyze_python_file(args.file, args.model, args.verbose)
        query_cost = calculate_cost(usage, args.model)
        cost_tracker.add_query_cost(query_cost)
        console.print()
        console.print(Panel(
            Markdown(reply),
            title="[bold green]Code Analysis Results[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            width=console.width,
            padding=(1, 2)
        ))
        console.print()
        console.print(render_search_results(search_results, reply))
        console.print()
        console.print(f"[italic gray]Time taken: {time_taken:.2f} seconds[/italic gray]")
        console.print()
        info_text = cost_tracker.get_info_text(args.model, query_cost, now)
        console.print(Panel(info_text, title="Query Info", border_style="blue"))
        console.print()
    
    if args.prompt:
        prompt_text = " ".join(args.prompt)
        console.print(Panel(
            Align.center(f"[bold cyan]{prompt_text}[/bold cyan]", vertical="middle"),
            title="[bold magenta]Your Query[/bold magenta]",
            border_style="medium_purple",
            box=box.ROUNDED,
            width=console.width,
            padding=(1, 2)
        ))
        reply, search_results, usage, time_taken = call_perplexity_api(prompt_text, args.model, args.verbose)
        query_cost = calculate_cost(usage, args.model)
        cost_tracker.add_query_cost(query_cost)
        console.print()
        console.print(Panel(
            Markdown(reply),
            title="[bold green]Perplexity Response[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            width=console.width,
            padding=(1, 2)
        ))
        console.print()
        console.print(render_search_results(search_results, reply))
        console.print()
        if args.copy_code:
            if pyperclip is None:
                console.print("[red]Error: pyperclip is required for code copying. Please install it with 'pip install pyperclip'.[/red]")
            else:
                code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', reply, re.DOTALL)
                if code_blocks:
                    code_to_copy = "\n\n".join(code_blocks)
                    pyperclip.copy(code_to_copy)
                    console.print("[green]Code copied to clipboard.[/green]")
                else:
                    console.print("[yellow]No code found in the response.[/yellow]")
        console.print(f"[italic gray]Time taken: {time_taken:.2f} seconds[/italic gray]")
        console.print()
        info_text = cost_tracker.get_info_text(args.model, query_cost, now)
        console.print(Panel(info_text, title="Query Info", border_style="blue"))
        console.print()

if __name__ == "__main__":
    main()
