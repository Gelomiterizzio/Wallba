"""Proceso agente aislado: ejecuta un guion contra la API con su bearer scoped.

Uso: python -m wallba.agent.worker --scenario S04 --seed 7
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from wallba.agent.http_gateway import GatewayRejected, HttpToolGateway
from wallba.agent.scripted import AGENT_KIND_LABEL, ScriptedAgent
from wallba.foundation.config import load_settings


def run_script(gateway: HttpToolGateway, scenario: str, seed: int, run_id: str) -> list[dict[str, str]]:
    agent = ScriptedAgent(run_id, seed)
    outcomes: list[dict[str, str]] = []
    for call in agent.plan(scenario):
        key = str(uuid.uuid5(uuid.UUID(call.request_id), "idempotency"))
        try:
            view = gateway.submit(call, None, key)
            outcomes.append({"request_id": call.request_id, "state": view.state})
        except GatewayRejected as exc:
            outcomes.append({"request_id": call.request_id, "state": "REJECTED", "code": exc.code})
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=AGENT_KIND_LABEL)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    settings = load_settings()
    if settings.role != "agent":
        print("el worker requiere WALLBA_ROLE=agent", file=sys.stderr)
        return 2
    gateway = HttpToolGateway(settings.api_url, settings.agent_bearer)
    outcomes = run_script(gateway, args.scenario, args.seed, str(uuid.uuid4()))
    print(json.dumps({"agent": AGENT_KIND_LABEL, "outcomes": outcomes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
