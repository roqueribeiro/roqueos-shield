"""Helper compartilhado pra cleanup de adapters subprocess.

Padrao em todos os adapters CLI (nmap, nuclei, trivy, gitleaks, ...): cada
`start_scan` cria um asyncio.Task que aguarda o subprocess e um diretorio
temporario pra outputs. Sem cleanup explicito, ambos vazam:

- O task fica em `self._tasks[native_id]` indefinidamente apos o scan terminar.
- O temp dir nao e' removido — uma stack de longa duracao acumula GB.
- Excecoes nao-resgatadas no task ficam "orphan" e poluem o evento loop.

`cleanup_subprocess_handle()` resolve os 3.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


async def cleanup_subprocess_handle(
    *,
    native_id: str,
    tasks: dict[str, asyncio.Task[object]],
    output_paths: dict[str, Path] | None = None,
    adapter_name: str = "unknown",
) -> None:
    """Limpa task + diretorio temp associado a um native_id.

    Args:
        native_id: ID retornado por start_scan (PID, hash, ou afins).
        tasks: dict do adapter (`self._tasks`).
        output_paths: dict opcional do adapter (`self._xml_paths`, `_outputs`...).
            O diretorio PAI do path eh removido (mkdtemp gera dir/arquivo).
        adapter_name: pra logging.
    """
    # 1. Mata os PROCESSOS FILHOS antes de cancelar a task.
    # Cancelar a Task interrompe o `await communicate()`, NAO o processo. Medido:
    # cleanup retornava em 0.00s, o workdir era removido, e o processo continuava
    # escrevendo num diretorio que ja nao existe. Com clone completo por padrao, um
    # repo grande que estoure os 1800s deixava um `git clone` orfao consumindo rede e
    # disco, sem dono — a tela dizendo "estourou o timeout" e a maquina ainda
    # clonando. O `finally` do `_run_adapter` dispara isto em TODO caminho de falha.
    await _matar_filhos(native_id=native_id, adapter_name=adapter_name)

    # 2. Cancela task se ainda esta rodando; aguarda morrer.
    task = tasks.pop(native_id, None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as e:  # noqa: BLE001
            log.debug(
                "adapter.cleanup.task_drained",
                adapter=adapter_name,
                native_id=native_id,
                error=str(e),
            )
    elif task is not None and task.done():
        # Drena excecao nao-resgatada pra evitar warning "Task exception was
        # never retrieved" do asyncio. Logamos em debug — eh esperado em scans
        # que falharam mas ja foram tratados pelo poll/normalize.
        try:
            _ = task.result()
        except BaseException as e:  # noqa: BLE001
            log.debug(
                "adapter.cleanup.task_drained_exception",
                adapter=adapter_name,
                native_id=native_id,
                error=str(e),
            )

    # 2. Remove diretorio temporario.
    # Heuristica: se o caminho aponta pra arquivo (suffix conhecido), removemos
    # o diretorio pai (padrao mkdtemp/file.json). Se aponta pra diretorio, remove
    # diretamente. Em ambos os casos, preferimos remover a hierarquia inteira
    # criada pelo mkdtemp prefixado com "cai-".
    if output_paths is not None:
        out = output_paths.pop(native_id, None)
        if out is not None:
            if out.is_dir():
                target_dir = out
            elif out.suffix:  # arquivo (xml, json, jsonl)
                target_dir = out.parent
            else:
                # nao podemos decidir; tenta os dois
                target_dir = out.parent if not out.exists() or out.is_file() else out
            # Salvaguarda: so remove se for um caminho temp do CAI ("cai-" prefix)
            # OU se for sob /tmp. Evita rm acidental de paths arbitrarios.
            if target_dir.exists() and (
                "cai-" in target_dir.name or "cai-" in (target_dir.parent.name or "")
            ):
                shutil.rmtree(target_dir, ignore_errors=True)
                log.debug(
                    "adapter.cleanup.tmp_removed",
                    adapter=adapter_name,
                    path=str(target_dir),
                )


async def _matar_filhos(*, native_id: str, adapter_name: str) -> None:
    """Termina os subprocessos que este processo ainda tem vivos.

    O asyncio guarda os filhos no watcher do event loop; aqui pegamos os
    `asyncio.subprocess.Process` que ainda nao sairam e mandamos SIGTERM, com SIGKILL
    depois de um instante. Sem isto, o cancelamento da Task deixa o binario rodando.
    """
    import contextlib

    vivos = [p for p in _PROCESSOS.pop(native_id, []) if p.returncode is None]
    if not vivos:
        return
    for proc in vivos:
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.terminate()
    _, pendentes = await asyncio.wait([asyncio.create_task(p.wait()) for p in vivos], timeout=3.0)
    for t in pendentes:
        t.cancel()
    for proc in vivos:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
    log.info(
        "adapter.cleanup.processos_encerrados",
        adapter=adapter_name,
        native_id=native_id,
        quantos=len(vivos),
    )


# Registro de subprocessos por handle. O adapter chama `registrar_processo` logo
# depois de criar o processo; o cleanup usa isto para matar o que sobrou.
_PROCESSOS: dict[str, list[Any]] = {}


def registrar_processo(native_id: str, proc: Any) -> None:
    """Associa um subprocesso ao handle, para o cleanup poder termina-lo."""
    _PROCESSOS.setdefault(native_id, []).append(proc)
