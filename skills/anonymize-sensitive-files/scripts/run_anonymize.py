#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_VENV = SKILL_DIR / ".venv"
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
CLI = SCRIPT_DIR / "anonymize_files.py"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = remove_flag(args, "--dry-run")
    no_install = remove_flag(args, "--no-install")
    venv_dir = parse_option(args, "--venv", DEFAULT_VENV)
    python_path = venv_python(venv_dir)

    steps = ["venv"]
    if not no_install:
        steps.append("install")
    command = [str(python_path), str(CLI), *args]

    if dry_run:
        print(
            json.dumps(
                {
                    "venv_dir": str(venv_dir),
                    "python": str(python_path),
                    "requirements": str(REQUIREMENTS),
                    "steps": steps,
                    "command": command,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    ensure_venv(venv_dir)
    if not no_install:
        install_requirements(python_path)

    completed = subprocess.run(command)
    return completed.returncode


def remove_flag(args: list[str], flag: str) -> bool:
    if flag not in args:
        return False
    args.remove(flag)
    return True


def parse_option(args: list[str], option: str, default: Path) -> Path:
    if option not in args:
        return default
    index = args.index(option)
    try:
        value = args[index + 1]
    except IndexError as exc:
        raise SystemExit(f"{option} requires a path value") from exc
    del args[index : index + 2]
    return Path(value).expanduser().resolve()


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv(venv_dir: Path) -> None:
    python_path = venv_python(venv_dir)
    if python_path.exists():
        return
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)


def install_requirements(python_path: Path) -> None:
    subprocess.run([str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS)], check=True)


if __name__ == "__main__":
    raise SystemExit(main())
