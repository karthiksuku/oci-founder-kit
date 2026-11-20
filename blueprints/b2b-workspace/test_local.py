"""Exercise B2B authorization and the portal with a new Unix-socket-only PostgreSQL cluster."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def verify(postgres_bin, browser=False):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Install Node 22+ and the Taskboard reference dependencies.")
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="founder-b2b-", dir="/tmp") as tmp:
        socket = Path(tmp) / "socket"
        socket.mkdir(mode=0o700)
        data = Path(tmp) / "database"
        subprocess.run([postgres_bin / "initdb", "-D", data, "-U", "fixture_owner", "-A", "trust", "--no-instructions"],
                       check=True, capture_output=True, timeout=45)
        subprocess.run([postgres_bin / "pg_ctl", "-D", data, "-l", Path(tmp) / "postgres.log",
                        "-o", f"-k {socket} -h '' -p 55439", "-w", "start"], check=True, capture_output=True, timeout=30)
        try:
            env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "FOUNDER_B2B_SOCKET": str(socket)}
            if browser:
                env["FOUNDER_B2B_BROWSER"] = "1"
                if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
                    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
            subprocess.run([node, "--test", root / "acceptance.mjs"], env=env, check=True, timeout=150)
        finally:
            subprocess.run([postgres_bin / "pg_ctl", "-D", data, "-m", "immediate", "-w", "stop"],
                           check=True, capture_output=True, timeout=30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", type=Path, required=True)
    parser.add_argument("--browser", action="store_true", help="Also exercise the actual workspace page in local Chromium")
    args = parser.parse_args()
    verify(args.postgres_bin.resolve(strict=True), args.browser)
