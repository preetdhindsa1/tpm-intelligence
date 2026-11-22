"""Team connector configs: plug a cross-functional team in with YAML, not core forks.

Kubernetes and (later) Kafka are example teams. Downstream pipeline/engine/api stay
source-agnostic; only collectors and linker packs are team-shaped.
"""

from connectors.load import load_team, load_teams, teams_dir
from connectors.schema import TeamConfig

__all__ = ["TeamConfig", "load_team", "load_teams", "teams_dir"]
