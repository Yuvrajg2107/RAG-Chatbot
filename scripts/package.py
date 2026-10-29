"""Package only project deliverables, never secrets, uploads, caches, or local agent state."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    ".vercelignore",
    "vercel.json",
    "Dockerfile",
    "start.cmd",
    "start.ps1",
]
DIRECTORIES = ["app", "static", "scripts", "tests", "samples", "evaluation", "docs", ".github"]


def package(destination=None):
    destination = Path(destination or ROOT / "dist/margin-rag-submission.zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidates = [ROOT / filename for filename in FILES]
    for name in DIRECTORIES:
        candidates.extend((ROOT / name).rglob("*"))
    for name in [
        "dependency-audit.json",
        "browser-checks.json",
        "hosted-browser-checks.json",
        "hosted-api-checks.json",
        "gemini-key-check.json",
        "gemini-live-checks.json",
        "gemini-browser-checks.json",
        "tests.xml",
        "sample-pdf-contact-sheet.png",
    ]:
        evidence = ROOT / "artifacts" / name
        if evidence.exists():
            candidates.append(evidence)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for source in sorted(set(candidates)):
            if source.is_symlink() or not source.is_file():
                continue
            relative = source.relative_to(ROOT)
            private_parts = {"__pycache__", ".vercel", ".git", ".venv", ".cache", ".model-cache"}
            if private_parts.intersection(relative.parts) or source.suffix == ".pyc":
                continue
            if source.name.startswith(".env") and source.name != ".env.example":
                continue
            archive.write(source, "margin-rag/" + relative.as_posix())
    print(f"Source submission package: {destination}")
    return destination


if __name__ == "__main__":
    package()
