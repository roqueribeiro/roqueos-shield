"""O nmap roda sem root e sem NET_RAW (#12): o connect scan precisa estar explícito."""

from __future__ import annotations

from orchestrator.adapters.nmap_adapter import NmapAdapter


def test_default_args_fazem_connect_scan() -> None:
    args = NmapAdapter.DEFAULT_ARGS
    assert "-sT" in args
    assert "-sS" not in args
    assert "-Pn" in args
