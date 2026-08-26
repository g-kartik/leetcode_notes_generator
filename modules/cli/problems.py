"""`problems` command group: fetch, store, and render LeetCode problem data.

Nests one subgroup and several flat commands:
  - `problems data`              fetching + pending-cache bookkeeping
                                  (`fetch`, `pending sync/count/list/show/clear`)
  - flat commands on `problems`  operate on data already stored:
                                  `list`, `show`, `count`, `delete`, `render`,
                                  `recent`
"""

from .root import cli


@cli.group()
def problems() -> None:
    """Fetch, store, and render LeetCode problem data."""
