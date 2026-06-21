import pathlib
import os
from vaultmind.orchestrator import run_orchestrator

run_orchestrator(
    vault_root=pathlib.Path(os.getenv("VAULTMIND_VAULT_ROOT", "./vault")),
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    seed=os.getenv("AGENT_SEED_PHRASE", "vaultmind-orchestrator-seed-phrase-01"),
)
