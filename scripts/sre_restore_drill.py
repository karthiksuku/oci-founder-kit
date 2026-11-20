#!/usr/bin/env python3
"""Restore a synthetic Taskboard DB into a second isolated local PostgreSQL cluster.

No existing DSN, TCP listener, production data or cloud access. Local toolchain
rehearsal only: this does not test the customer's backup service or meet an RPO.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


def drill(bindir):
    bindir = Path(bindir).resolve(strict=True)
    tools = {n: str((bindir / n).resolve(strict=True)) for n in
             ("initdb", "pg_ctl", "psql", "pg_dump", "pg_restore")}
    with tempfile.TemporaryDirectory(prefix="kit-restore-") as tmp, contextlib.ExitStack() as cleanup:
        root = Path(tmp)
        env = {"PATH": "/usr/bin:/bin", "HOME": tmp, "LC_ALL": "C", "PGCONNECT_TIMEOUT": "3"}
        def run(tool, *args, raw=None):
            return subprocess.run([tools[tool], *map(str, args)], input=raw, env=env, cwd=tmp,
                                  capture_output=True, timeout=60, check=True).stdout
        def cluster(name):
            folder = root / name; folder.mkdir(mode=0o700)
            data = folder / "data"
            run("initdb", "-D", data, "-U", "drill", "--auth=trust", "--no-instructions")
            if not re.fullmatch(r"/[A-Za-z0-9/_-]+", str(folder)):
                raise ValueError("Unsafe temporary path for PostgreSQL.")
            run("pg_ctl", "-D", data, "-o", f"-h '' -k {folder} -p 55439", "-l", folder / "pg.log", "-w", "start")
            cleanup.callback(run, "pg_ctl", "-D", data, "-m", "fast", "-w", "stop")
            return ["-h", str(folder), "-p", "55439", "-U", "drill", "-d", "postgres"]
        source = cluster("source")
        def sql(target, statement):
            return run("psql", "-XAt", "-v", "ON_ERROR_STOP=1", *target, "-c", statement).strip()
        sql(source, "CREATE TABLE tasks(id integer PRIMARY KEY, owner_name text, title text, done boolean); "
                    "INSERT INTO tasks VALUES(1,'one','synthetic first',false),(2,'two','synthetic second',true)")
        query = "SELECT id,owner_name,title,done FROM tasks ORDER BY id"
        expected = sql(source, query)
        baseline = time.monotonic()
        archive = root / "fixture.dump"
        run("pg_dump", *source, "--format=custom", "--file", archive)
        sql(source, "INSERT INTO tasks VALUES(3,'one','after backup',false)")
        start = time.monotonic(); isolated = cluster("restore")
        run("pg_restore", *isolated, "--exit-on-error", "--no-owner", archive)
        if not expected or sql(isolated, query) != expected or sql(source, "SELECT count(*) FROM tasks") != b"3":
            raise ValueError("Restore contents did not match the backup boundary.")
        now = time.monotonic()
        return {"schema": "oci-kit-local-restore-drill/1", "status": "passed", "scope": "synthetic-postgres-only",
                "separate_source_and_target": True, "restore_elapsed_seconds": round(now-start, 3),
                "fixture_backup_age_seconds": round(now-baseline, 3), "restored_rows": 2,
                "post_backup_row_excluded": True, "cloud_writes": False, "production_recovery_verified": False}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--postgres-bin", type=Path, required=True)
    try:
        print(json.dumps(drill(cli.parse_args().postgres_bin), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError):
        cli.exit(3, "Local restore drill unavailable or failed; no production evidence. Check the PostgreSQL binaries and local socket permissions.\n")
