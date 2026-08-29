"""Semgrep adapter — SAST de código-fonte (o que faltava para "qualidade de código").

Diferente dos scanners de secret (gitleaks/trufflehog), IaC (checkov) e CVE de deps
(trivy), o Semgrep lê o CÓDIGO atrás de bug/vuln: injection, SSRF, path traversal,
crypto fraca, desserialização, uso perigoso de API. Roda sobre um checkout local
(clona a URL do repo, ou usa um diretório já presente).

Soberania: `--metrics off` — nada é enviado pro registry da Semgrep.

O default NÃO é `auto`. Medido nesta máquina (semgrep 1.x):

    $ semgrep scan --config auto --metrics off ...
    [ERROR]: Cannot create auto config when metrics are off.  → exit 2

Ou seja: `auto` e a postura de soberania deste projeto são incompatíveis, e o
default antigo (`auto`) fazia o ÚNICO scanner que lê o código falhar em 100% das
execuções. O default agora são os mesmos packs que o CI usa para escanear este
repo — `p/security-audit`, `p/secrets` e `p/owasp-top-ten` (330 regras; no alvo de
teste acha injeção de comando, SQLi por taint, pickle, MD5 e debug ligado).

Sem egress para o registry, aponte para um pack local:
`{"config": "/rules"}` ou `{"config": ["/rules/py", "/rules/tf"]}`.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)

log = structlog.get_logger(__name__)

_SEVERITY_MAP: dict[str, Severity] = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
}
_CONFIDENCE_MAP: dict[str, Confidence] = {
    "HIGH": Confidence.CERTAIN,
    "MEDIUM": Confidence.FIRM,
    "LOW": Confidence.TENTATIVE,
}
_CWE_RE = re.compile(r"CWE-\d+")

# Os mesmos packs do job `self-scan` do CI: o que a ferramenta roda contra o código
# dos outros é o que ela roda contra si mesma. Usados quando NÃO há ruleset local —
# exigem alcançar o registry da Semgrep.
_DEFAULT_CONFIGS: tuple[str, ...] = ("p/security-audit", "p/secrets", "p/owasp-top-ten")


# Ruleset embarcado na imagem (`semgrep-rules`, LGPL-2.1, pinado no Dockerfile).
# Preferido sobre os packs: num banco a rede é restrita, e `--config p/...` exige
# alcançar o registry. Medido: sem egress o semgrep sai com código 0 e ZERO regras —
# o silêncio que o `_rules_ran` pega, mas que deixaria o SAST inútil justamente no
# ambiente-alvo. Com o ruleset local, 1000+ regras rodam offline.
def _dir_regras_local() -> Path:
    """Caminho do ruleset embarcado. Lido a cada chamada: o valor vem do Settings
    (e do ambiente), e fixá-lo no import esconderia mudança de configuração."""
    from orchestrator.config import settings

    return Path(os.environ.get("SEMGREP_RULES_DIR") or settings.SEMGREP_RULES_DIR)


# Diretórios validados um a um com `semgrep --validate` (elixir fica de fora: as
# regras dele exigem uma extensão proprietária que não vem no pacote open source).
# A raiz do repo NÃO serve: ela tem diretórios com config inválida, e passar a raiz
# faz o semgrep abortar com "1 configs were invalid" e ZERO regras.
_LINGUAGENS: dict[str, tuple[str, ...]] = {
    "python": (".py", ".pyi"),
    "javascript": (".js", ".jsx", ".mjs", ".cjs", ".vue"),
    "typescript": (".ts", ".tsx"),
    "java": (".java",),
    "go": (".go",),
    "ruby": (".rb", ".erb"),
    "php": (".php",),
    "csharp": (".cs",),
    "terraform": (".tf", ".tfvars"),
    "dockerfile": ("dockerfile",),
    "bash": (".sh", ".bash"),
    "rust": (".rs",),
    "kotlin": (".kt", ".kts"),
    "swift": (".swift",),
    "scala": (".scala", ".sbt"),
    "yaml": (".yml", ".yaml"),
    "json": (".json",),
    "html": (".html", ".htm"),
    "c": (".c", ".h"),
    "ocaml": (".ml", ".mli"),
    "clojure": (".clj", ".cljs"),
    # Regras agnósticas de linguagem (segredo, config perigosa): sempre entram.
    "generic": (),
}
_SEMPRE = ("generic",)


def _linguagens_do_checkout(raiz: Path, teto: int = 20000) -> set[str]:
    """Quais rulesets fazem sentido para ESTE checkout.

    Carregar as 1900 regras de todas as linguagens custa ~2min de parsing por scan,
    quase tudo desperdiçado: um repo Python não precisa das regras de Kotlin. Isto
    olha as extensões presentes e reduz o conjunto — sem tirar cobertura, porque
    regra de linguagem ausente não acharia nada mesmo.
    """
    por_ext: dict[str, str] = {}
    for ling, exts in _LINGUAGENS.items():
        for e in exts:
            por_ext[e] = ling
    achadas: set[str] = set(_SEMPRE)
    vistos = 0
    for caminho in raiz.rglob("*"):
        if vistos >= teto:
            break
        if not caminho.is_file():
            continue
        vistos += 1
        nome = caminho.name.lower()
        ling = por_ext.get(caminho.suffix.lower())
        if ling is None and nome.startswith("dockerfile"):
            ling = "dockerfile"
        if ling:
            achadas.add(ling)
    return achadas


def _configs_locais(raiz_alvo: Path | None = None) -> list[str]:
    """Diretórios do ruleset local que existem e interessam ao alvo; [] se não houver."""
    raiz_regras = _dir_regras_local()
    if not raiz_regras.is_dir():
        return []
    querer = (
        _linguagens_do_checkout(raiz_alvo)
        if raiz_alvo is not None and raiz_alvo.is_dir()
        else set(_LINGUAGENS)
    )
    return [str(raiz_regras / ling) for ling in sorted(querer) if (raiz_regras / ling).is_dir()]


def _resolver_configs(bruto: Any, raiz_alvo: Path | None = None) -> list[str]:
    """Normaliza `options["config"]` (str, lista ou ausente) para uma lista.

    Sem config explícito: ruleset LOCAL se a imagem o trouxer (funciona sem egress),
    senão os packs do registry. Recusa `auto` com mensagem explícita em vez de deixar
    o semgrep sair 2 com um erro que ninguém liga ao `--metrics off` daqui.
    """
    if bruto is None or bruto == "":
        configs = _configs_locais(raiz_alvo) or list(_DEFAULT_CONFIGS)
    elif isinstance(bruto, str):
        configs = [bruto]
    else:
        configs = [str(x) for x in bruto]
    if any(c.strip().lower() == "auto" for c in configs):
        raise ValueError(
            "semgrep: `--config auto` exige telemetria ligada e este projeto roda com "
            "`--metrics off` (soberania de dados) — a combinação sai com erro e NENHUMA "
            "regra roda. Use packs explícitos (o default: "
            + ", ".join(_DEFAULT_CONFIGS)
            + ") ou um caminho local."
        )
    return configs


class SemgrepAdapter:
    """Roda semgrep sobre um repo (clone efêmero) ou diretório local; JSON → Finding."""

    name = "semgrep"

    def __init__(self, semgrep_bin: str | None = None, git_bin: str | None = None) -> None:
        self.semgrep_bin = semgrep_bin or shutil.which("semgrep") or "semgrep"
        self.git_bin = git_bin or shutil.which("git") or "git"
        self._tasks: dict[str, asyncio.Task[tuple[int, Path]]] = {}
        self._workdirs: dict[str, Path] = {}

    async def health(self) -> bool:
        try:
            p = await asyncio.create_subprocess_exec(
                self.semgrep_bin,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await p.communicate()
            return p.returncode == 0
        except OSError:  # binário ausente, sem permissão, e os primos do OSError
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        if target.asset_type != AssetType.REPO:
            raise ValueError(f"semgrep só suporta REPO, recebi {target.asset_type}")

        workdir = Path(tempfile.mkdtemp(prefix="cai-semgrep-"))
        report_path = workdir / "report.json"
        depth = str(options.get("clone_depth", 1))

        # Diretório local já presente (path) vs. URL de repo a clonar.
        local_dir = Path(target.value)
        use_local = local_dir.is_dir()
        clone_dir = local_dir if use_local else (workdir / "repo")
        # Só dá pra detectar linguagem quando o código já está em disco; num clone,
        # a seleção acontece depois (dentro de `_run`).
        configs = _resolver_configs(options.get("config"), local_dir if use_local else None)

        async def _run() -> tuple[int, Path]:
            if not use_local:
                clone = await asyncio.create_subprocess_exec(
                    self.git_bin,
                    "clone",
                    "--quiet",
                    "--depth",
                    depth,
                    target.value,
                    str(clone_dir),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await clone.communicate()
                if clone.returncode != 0:
                    log.error("semgrep.clone_failed", err=stderr.decode(errors="replace")[:500])
                    return clone.returncode or 1, report_path

            # Repo clonado: só agora dá pra ver quais linguagens ele tem.
            escolhidas = configs
            if not use_local and not options.get("config"):
                escolhidas = _resolver_configs(None, clone_dir)
            args = [self.semgrep_bin, "scan"]
            for c in escolhidas:
                args.extend(["--config", c])
            scan = await asyncio.create_subprocess_exec(
                *args,
                "--json",
                "--output",
                str(report_path),
                "--quiet",
                "--metrics",
                "off",
                "--disable-version-check",
                # `--time` põe em `time.rules` quantas regras REALMENTE rodaram. É o
                # único sinal que separa "código limpo" de "nenhuma regra carregou"
                # — ver `_rules_ran` abaixo.
                "--time",
                str(clone_dir),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await scan.communicate()
            # semgrep sai 0 mesmo com findings (eles vão pro JSON). >1 é erro real.
            rc = scan.returncode or 0
            if rc > 1:
                log.error("semgrep.scan_failed", rc=rc, err=stderr.decode(errors="replace")[:500])
                return rc, report_path
            return 0, report_path

        native_id = str(uuid4())
        self._workdirs[native_id] = workdir
        self._tasks[native_id] = asyncio.create_task(_run())
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"repo": target.value, "report": str(report_path), "config": configs},
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        rc, _ = task.result()
        return ScanStatus.DONE if rc == 0 else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        _, report_path = self._tasks[handle.native_id].result()
        if not report_path.exists():
            raise ScanIntegrityError(
                "semgrep não escreveu o relatório: o SAST não rodou. Zero achados aqui "
                "NÃO significa código sem vulnerabilidade."
            )
        texto = report_path.read_text(encoding="utf-8").strip()
        if not texto:
            raise ScanIntegrityError("relatório do semgrep vazio: execução interrompida.")
        try:
            payload: dict[str, Any] = json.loads(texto) or {}
        except json.JSONDecodeError as e:
            raise ScanIntegrityError(
                f"relatório do semgrep não é JSON válido ({e}): resultado não confiável."
            ) from e

        # Zero achados só vale como "limpo" se ALGUMA regra rodou. Um `--config`
        # que não resolve (registry sem egress no cliente, pack privado sem
        # credencial, caminho errado) faz o semgrep sair com código 0, zero regras e
        # zero resultados — indistinguível de código são. Reproduzido: config com
        # `rules: []` dá exit 0 / 0 regras / 0 achados. Num banco, egress restrito é
        # o caso normal, então este silêncio seria o comportamento padrão.
        if not _rules_ran(payload):
            raise ScanIntegrityError(
                "semgrep terminou sem carregar NENHUMA regra: o resultado seria um "
                "'limpo' falso. Verifique o --config (registry alcançável? pack "
                "existe? caminho local correto?)."
            )
        return RawResults(adapter=self.name, payload=payload)

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()
        results = (raw.payload or {}).get("results", []) if isinstance(raw.payload, dict) else []

        for item in results:
            extra = item.get("extra", {}) or {}
            meta = extra.get("metadata", {}) or {}
            check_id = item.get("check_id", "semgrep-rule")
            path = item.get("path", "?")
            line = (item.get("start", {}) or {}).get("line", "?")

            findings.append(
                Finding(
                    scan_id=placeholder,
                    target=Target(asset_type=AssetType.REPO, value=f"{path}:{line}"),
                    source_tool=self.name,
                    source_rule_id=check_id,
                    cwe=_extract_cwes(meta.get("cwe")),
                    title=_short_title(check_id, extra.get("message", "")),
                    description=(
                        f"{extra.get('message', '').strip()}\n"
                        f"Arquivo {path}, linha {line}."
                        + (f" OWASP: {_join(meta.get('owasp'))}." if meta.get("owasp") else "")
                    ).strip(),
                    severity=_SEVERITY_MAP.get(
                        str(extra.get("severity", "INFO")).upper(), Severity.LOW
                    ),
                    confidence=_CONFIDENCE_MAP.get(
                        str(meta.get("confidence", "")).upper(), Confidence.FIRM
                    ),
                    evidence=[
                        Evidence(
                            description=f"Match da regra {check_id} em {path}:{line}",
                            snippet=(extra.get("lines") or "")[:400],
                        )
                    ],
                )
            )
        log.info("semgrep.normalize_done", findings=len(findings))
        return findings

    async def cleanup(self, handle: ScanHandle) -> None:
        from orchestrator.adapters._cleanup import cleanup_subprocess_handle

        await cleanup_subprocess_handle(
            native_id=handle.native_id,
            tasks=self._tasks,  # type: ignore[arg-type]
            output_paths=self._workdirs,
            adapter_name=self.name,
        )


def _rules_ran(payload: dict[str, Any]) -> int:
    """Quantas regras o semgrep realmente executou (`--time` popula `time.rules`)."""
    if not isinstance(payload, dict):
        return 0
    regras = (payload.get("time") or {}).get("rules")
    return len(regras) if isinstance(regras, list) else 0


def _extract_cwes(raw: Any) -> list[str]:
    """Extrai só os identificadores `CWE-NNN` do metadata (que vem como str ou lista)."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for it in items:
        m = _CWE_RE.search(str(it))
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def _short_title(check_id: str, message: str) -> str:
    """Título curto: última parte do check_id + 1ª frase da mensagem."""
    rule = check_id.rsplit(".", 1)[-1].replace("-", " ")
    first = message.strip().split(". ")[0][:120]
    return f"{rule}: {first}" if first else rule or check_id


def _join(v: Any) -> str:
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
