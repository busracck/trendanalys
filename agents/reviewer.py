"""Kod inceleme ajanı: ruff + bandit + LLM.

    python -m agents.reviewer                  # HEAD ile çalışma alanı farkı
    python -m agents.reviewer --staged         # commit'e hazırlanan değişiklikler
    python -m agents.reviewer --range main..HEAD
    python -m agents.reviewer --staged --engelle   # blocker varsa commit'i durdur

Önce ruff ve bandit çalışır (kesin bulgular), sonra diff ve bulgular LLM'e
gönderilir (yorum gerektiren kısım). `blocker` bulgusu varsa çıkış kodu 1 olur.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from agents.providers import DEFAULT_MODELS, ProviderError, ask
from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
GUIDELINES_FILE = BASE_DIR / "agents" / "review_guidelines.md"

# LLM'e gönderilecek en uzun diff (karakter). Büyük diff'ler küçük modeli boğuyor.
MAX_DIFF_CHARS = 12000

SEVERITY_STYLE = {"blocker": "bold red", "major": "yellow", "minor": "dim cyan"}

PROMPT = """Sen bir Python projesinde kıdemli kod inceleyicisisin.
Aşağıdaki kuralları ve değişikliği inceleyip bulgularını JSON olarak döndür.

## Proje kuralları
{guidelines}

## Otomatik araç bulguları (ruff, bandit)
{lint}

## Değişiklik (git diff)
```diff
{diff}
```

## Cevap biçimi
Yalnızca şu yapıda JSON döndür, başka metin yazma:
{{"findings": [
  {{"severity": "blocker|major|minor", "file": "dosya/yolu.py", "line": 12,
    "message": "Sorun ve nasıl düzeltileceği, tek cümle."}}
]}}

Kurallar:
- Sadece diff'te eklenen veya değiştirilen satırlar hakkında konuş.
- Emin olmadığın şeyi yazma. Sorun yoksa boş liste döndür: {{"findings": []}}
- **Aynı bulguyu tekrarlama.** Her sorun listede bir kez geçsin.
- En fazla 8 bulgu yaz; en önemlilerini seç.
- Bir kuralı ihlal ettiğini iddia ediyorsan diff'teki hangi satırın ihlal ettiğini bil.
- Boş değerli ayar satırları (`API_KEY=`) gizli bilgi değildir, örnek dosyadır.
- Mesajları Türkçe yaz, tek cümle."""


console = Console()


def run(command):
    """Komutu çalıştırır, çıktısını döndürür. Hata kodları normal kabul edilir."""
    result = subprocess.run(command, capture_output=True, text=True, cwd=BASE_DIR)
    return result.stdout.strip()


# Yalnızca Python kodu inceleniyor: kurallar koda dair, ayar ve belge dosyaları değil
PYTHON_ONLY = ["--", "*.py"]


def get_diff(args):
    if args.range:
        return run(["git", "diff", args.range, *PYTHON_ONLY])
    if args.staged:
        return run(["git", "diff", "--cached", *PYTHON_ONLY])
    return run(["git", "diff", "HEAD", *PYTHON_ONLY])


def changed_files(args):
    """Diff'te geçen Python dosyaları."""
    if args.range:
        command = ["git", "diff", "--name-only", args.range, *PYTHON_ONLY]
    elif args.staged:
        command = ["git", "diff", "--cached", "--name-only", *PYTHON_ONLY]
    else:
        command = ["git", "diff", "--name-only", "HEAD", *PYTHON_ONLY]

    names = run(command).splitlines()
    return [name for name in names if name.endswith(".py") and (BASE_DIR / name).exists()]


def run_linters(files):
    """ruff ve bandit bulgularını tek bir metne toplar."""
    if not files:
        return "Değişen Python dosyası yok."

    lines = []

    ruff_raw = run([sys.executable, "-m", "ruff", "check", "--output-format", "json", *files])
    for item in json.loads(ruff_raw or "[]"):
        location = item.get("location") or {}
        lines.append(
            f"ruff {item['code']} {item['filename']}:{location.get('row', '?')} — {item['message']}"
        )

    bandit_raw = run([sys.executable, "-m", "bandit", "-f", "json", "-q", *files])
    for item in json.loads(bandit_raw or "{}").get("results", []):
        lines.append(
            f"bandit {item['test_id']} ({item['issue_severity']}) "
            f"{item['filename']}:{item['line_number']} — {item['issue_text']}"
        )

    return "\n".join(lines) if lines else "Otomatik araçlar bulgu üretmedi."


SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2}


def unique(findings):
    """Her konum için tek bulgu bırakır, en yüksek önem derecesini seçer.

    Küçük modeller aynı sorunu birkaç kez, hatta farklı önem dereceleriyle yazıyor.
    """
    best = {}
    for finding in findings:
        key = (finding.get("file"), finding.get("line"))
        current = best.get(key)
        if current is None or SEVERITY_ORDER.get(
            finding.get("severity"), 3
        ) < SEVERITY_ORDER.get(current.get("severity"), 3):
            best[key] = finding
    return list(best.values())


def show(findings, lint_output):
    if lint_output and "bulgu üretmedi" not in lint_output and "dosya yok" not in lint_output:
        console.print("\n[bold]Otomatik araçlar[/bold]")
        console.print(lint_output, style="dim")

    if not findings:
        console.print("\n[bold green]Bulgu yok.[/bold green]")
        return

    table = Table(title="\nKod inceleme bulguları", show_lines=False)
    table.add_column("önem", no_wrap=True)
    table.add_column("yer", no_wrap=True)
    table.add_column("bulgu")

    for finding in sorted(
        unique(findings), key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 3)
    ):
        severity = finding.get("severity", "minor")
        location = f"{finding.get('file', '?')}:{finding.get('line', '?')}"
        table.add_row(
            f"[{SEVERITY_STYLE.get(severity, 'white')}]{severity}[/]",
            location,
            finding.get("message", ""),
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Kod inceleme ajanı.")
    parser.add_argument("--staged", action="store_true", help="git diff --cached kullan")
    parser.add_argument("--range", help="Örn: main..HEAD")
    parser.add_argument(
        "--engelle",
        action="store_true",
        help="Blocker bulgu varsa çıkış kodu 1 döndür (pre-commit için)",
    )
    args = parser.parse_args()

    diff = get_diff(args)
    if not diff:
        console.print("[dim]İncelenecek değişiklik yok.[/dim]")
        return 0

    files = changed_files(args)
    lint_output = run_linters(files)

    if len(diff) > MAX_DIFF_CHARS:
        console.print(f"[dim]Diff {len(diff)} karakter, ilk {MAX_DIFF_CHARS} inceleniyor.[/dim]")
        diff = diff[:MAX_DIFF_CHARS]

    model = settings.REVIEWER_MODEL or DEFAULT_MODELS.get(settings.REVIEWER_PROVIDER, "?")
    console.print(f"[dim]{settings.REVIEWER_PROVIDER} · {model} · {len(files)} dosya[/dim]")

    prompt = PROMPT.format(
        guidelines=GUIDELINES_FILE.read_text(encoding="utf-8"),
        lint=lint_output,
        diff=diff,
    )

    try:
        answer = ask(prompt, settings)
    except ProviderError as error:
        # Anahtar yoksa ya da servis kapalıysa commit engellenmez, uyarı verilir
        console.print(f"\n[yellow]LLM incelemesi atlandı:[/yellow] {error}")
        show([], lint_output)
        return 0

    findings = answer.get("findings", []) if isinstance(answer, dict) else []
    show(findings, lint_output)

    blockers = [f for f in unique(findings) if f.get("severity") == "blocker"]
    if not blockers:
        return 0

    # Modelin yanılma payı var; commit'i ancak --engelle ile durduruyoruz
    if args.engelle:
        console.print(f"\n[bold red]{len(blockers)} blocker bulgu — commit durduruldu.[/bold red]")
        return 1

    console.print(
        f"\n[bold yellow]{len(blockers)} blocker bulgu.[/bold yellow] "
        "Commit engellenmedi; engellemek için --engelle kullan."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
