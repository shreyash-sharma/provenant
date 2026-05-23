"""
Telemetry stub — no data collected.

Usage stats are tracked via PyPI download counts and GitHub traffic.
"""


def ping_install(repo_path: str = "") -> None:
    pass


def record(**kwargs) -> None:
    pass


def maybe_ask_for_star(repo_path: str = "") -> None:
    return None
