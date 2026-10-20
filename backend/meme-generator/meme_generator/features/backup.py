"""Private application snapshots. Never change source or symlink-target permissions."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(state, output):
    state = Path(state).resolve()
    output = Path(output)
    if not state.is_dir() or output.is_symlink() or output.exists():
        raise ValueError("use an existing state directory and a new snapshot path")
    if output.resolve().is_relative_to(state):
        raise ValueError("snapshot must be outside the source state")
    output.mkdir(parents=True, mode=0o700)
    # chmod only the newly created real directory, never walk symlinks.
    output.chmod(0o700)
    shutil.copytree(
        state,
        output / "state",
        symlinks=True,
        ignore=shutil.ignore_patterns(
            "*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm", "storage.lock"
        ),
    )
    databases = []
    for source in state.rglob("*.sqlite3"):
        if source.is_symlink():
            raise ValueError("database symlinks require explicit operator review")
        relative = source.relative_to(state)
        target = output / "state" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        old = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        new = sqlite3.connect(target)
        try:
            old.backup(new)
            if new.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("database verification failed")
        finally:
            new.close()
            old.close()
        databases.append(str(relative))
    files = {}
    links = {}
    for p in (output / "state").rglob("*"):
        name = str(p.relative_to(output / "state"))
        if p.is_symlink():
            links[name] = str(p.readlink())
        elif p.is_file():
            files[name] = digest(p)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(state),
        "files": files,
        "symlinks": links,
        "databases": databases,
        "scope": "online SQLite backup and file snapshot; verify cross-file references and rehearse restore before release",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    return {"files": len(files), "symlinks": len(links), "databases": len(databases)}


def verify(output):
    output = Path(output).resolve()
    m = json.loads((output / "manifest.json").read_text())
    errors = []
    for name, expected in m["files"].items():
        p = output / "state" / name
        if (
            not p.resolve().is_relative_to(output / "state")
            or p.is_symlink()
            or not p.is_file()
            or digest(p) != expected
        ):
            errors.append(name)
    for name, target in m["symlinks"].items():
        p = output / "state" / name
        if not p.is_symlink() or str(p.readlink()) != target:
            errors.append(name)
    for name in m["databases"]:
        path = output / "state" / name
        if not path.resolve().is_relative_to(output / "state") or path.is_symlink():
            errors.append(name)
            continue
        try:
            db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    errors.append(name)
            finally:
                db.close()
        except sqlite3.Error:
            errors.append(name)
    return {
        "status": "failed" if errors else "passed",
        "files": len(m["files"]),
        "databases": len(m["databases"]),
        "errors": errors,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--state", required=True)
    create.add_argument("--output", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--output", required=True)
    a = p.parse_args()
    result = snapshot(a.state, a.output) if a.command == "create" else verify(a.output)
    print(json.dumps(result))
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
