"""
Database connection settings, read from the environment.

    export MOODLE_DB_NAME=moodle_convert
    export MOODLE_DB_USER=mooconvert
    export MOODLE_DB_PASS='...'
    export MOODLE_DB_HOST=localhost

The password is passed to mysql via MYSQL_PWD rather than -p on the command
line, so it does not show up in `ps` output while a multi-hour conversion runs.
"""

import os
import subprocess
import sys

DB_NAME = os.environ.get("MOODLE_DB_NAME", "")
DB_USER = os.environ.get("MOODLE_DB_USER", "")
DB_PASS = os.environ.get("MOODLE_DB_PASS", "")
DB_HOST = os.environ.get("MOODLE_DB_HOST", "localhost")


def require_config():
    """Exit with a clear message if the environment isn't set up."""
    missing = [
        name
        for name, value in (
            ("MOODLE_DB_NAME", DB_NAME),
            ("MOODLE_DB_USER", DB_USER),
        )
        if not value
    ]
    if missing:
        sys.exit(
            "Missing environment variables: {}\n"
            "See the docstring in dbconfig.py.".format(", ".join(missing))
        )


def run_query(query, database=None, raw=False):
    """
    Run a query and return stdout as text, or None if mysql errored.

    raw=True uses -N (no column headers), which is what the detection queries
    want. Byte-exact results should go through HEX() in the query itself
    rather than relying on how the client renders them.
    """
    cmd = ["mysql", "-u", DB_USER, "-h", DB_HOST, "-D", database or DB_NAME]
    if raw:
        cmd.append("-N")
    cmd.extend(["-e", query])

    env = dict(os.environ)
    if DB_PASS:
        env["MYSQL_PWD"] = DB_PASS

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, env=env
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("MySQL error running query:")
        print("  {}".format(query[:200].replace("\n", " ")))
        print("  {}".format(e.stderr.strip()))
        return None
