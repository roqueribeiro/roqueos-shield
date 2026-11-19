"""Código enviado para scan: o tarball que um agente ou o CI manda, e o que fazer com ele.

O scan de REPO sabia clonar uma URL git. Código que um agente está escrevendo e ainda
não commitou, ou repo privado sem credencial no worker, não chegava ao scanner. O
caminho é o cliente empacotar a árvore (`roqueshield scan code .`) e mandar um
`.tar.gz`. Este módulo decide o que entra e o que é recusado; é puro (sem banco, sem
rede), para ser testado sem servidor.

Um tarball é entrada hostil. Recusado sem extrair nada:

- caminho absoluto, `..`, ou que sai da raiz depois de normalizado (path traversal);
- link simbólico ou hardlink que aponta para fora da raiz;
- dispositivo, FIFO, qualquer coisa que não seja arquivo, pasta ou link;
- mais arquivos que `CODE_UPLOAD_MAX_FILES`, ou mais bytes descomprimidos que
  `CODE_UPLOAD_MAX_EXTRACTED_MB` (bomba de compressão: o tamanho vem do cabeçalho de
  cada membro, que é exatamente o que o `tarfile` escreve no disco);
- tarball sem nenhum arquivo. Zero arquivo não é "código limpo": é envio quebrado.

A extração usa o filtro `data` do `tarfile` (PEP 706) por cima dessas checagens, como
segunda camada: se uma escapar, o filtro recusa.

A identidade do achado (`Finding._build_dedup_key`) usa o `target.value`, que para
REPO carrega o caminho do arquivo. Cada envio extrai numa pasta temporária diferente,
então o achado ganharia uma chave nova a cada scan e nada seria "conhecido". O
`reescrever_alvo` troca o prefixo da pasta pelo alvo lógico (`code://<projeto>`) e
recalcula a chave: o mesmo problema no mesmo arquivo tem a mesma chave em todo envio,
e o caminho do servidor não vaza para o relatório.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.domain.schemas import Finding, Target

ESQUEMA = "code://"
_PROJETO = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class CodigoRecusado(ValueError):
    """O envio não serve para scan. A mensagem diz por quê, para o cliente corrigir."""


def validar_projeto(nome: str) -> str:
    """Nome do projeto em minúsculas, letras, dígitos, `.`, `_` e `-`, até 64."""
    n = (nome or "").strip().lower()
    if not _PROJETO.match(n) or ".." in n:
        raise CodigoRecusado(
            "projeto deve ter de 1 a 64 caracteres: minúsculas, dígitos, '.', '_' e '-', "
            "começando por letra ou dígito"
        )
    return n


def alvo_do_projeto(projeto: str) -> str:
    return f"{ESQUEMA}{validar_projeto(projeto)}"


def projeto_do_alvo(valor: str) -> str | None:
    """O projeto de um alvo `code://<projeto>`, ou None se o alvo não é desse tipo."""
    if not valor.startswith(ESQUEMA):
        return None
    return validar_projeto(valor[len(ESQUEMA) :])


@dataclass(frozen=True)
class Inventario:
    arquivos: int
    bytes_descomprimidos: int


def _dentro(nome: str) -> bool:
    if nome.startswith("/") or "\\" in nome:
        return False
    normal = posixpath.normpath(nome)
    return not (normal == ".." or normal.startswith("../"))


def inspecionar(caminho: Path, *, max_arquivos: int, max_bytes: int) -> Inventario:
    """Lê o índice do tarball e recusa o que não pode ser extraído. Não escreve nada."""
    arquivos = 0
    total = 0
    try:
        with tarfile.open(caminho, mode="r:gz") as tar:
            for m in tar:
                if not _dentro(m.name):
                    raise CodigoRecusado(f"caminho fora da raiz no tarball: {m.name!r}")
                if m.issym() or m.islnk():
                    destino = (
                        posixpath.join(posixpath.dirname(m.name), m.linkname)
                        if m.issym()
                        else m.linkname
                    )
                    if m.linkname.startswith("/") or not _dentro(destino):
                        raise CodigoRecusado(
                            f"link que aponta para fora da raiz: {m.name!r} -> {m.linkname!r}"
                        )
                    continue
                if m.isdir():
                    continue
                if not m.isfile():
                    raise CodigoRecusado(
                        f"tipo de membro não aceito (só arquivo, pasta e link): {m.name!r}"
                    )
                arquivos += 1
                total += m.size
                if arquivos > max_arquivos:
                    raise CodigoRecusado(f"mais de {max_arquivos} arquivos no envio")
                if total > max_bytes:
                    raise CodigoRecusado(
                        f"o envio descomprimido passa de {max_bytes // (1024 * 1024)} MB"
                    )
    except (tarfile.TarError, EOFError, OSError) as e:
        raise CodigoRecusado(f"não é um .tar.gz legível: {e}") from e
    if arquivos == 0:
        raise CodigoRecusado(
            "o envio não tem nenhum arquivo: zero arquivo não é código limpo, é envio quebrado"
        )
    return Inventario(arquivos=arquivos, bytes_descomprimidos=total)


def extrair(caminho: Path, destino: Path, *, max_arquivos: int, max_bytes: int) -> Inventario:
    """Reinspeciona (o arquivo pode ter mudado no disco desde o upload) e extrai."""
    inv = inspecionar(caminho, max_arquivos=max_arquivos, max_bytes=max_bytes)
    destino.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(caminho, mode="r:gz") as tar:
            tar.extractall(destino, filter="data")
    except (tarfile.TarError, OSError) as e:
        raise CodigoRecusado(f"a extração falhou: {e}") from e
    return inv


def fotografar_em_git(raiz: Path) -> None:
    """Faz da árvore extraída um repositório git com UM commit.

    Os scanners de REPO (gitleaks, trufflehog) clonam e varrem o histórico: numa pasta
    sem `.git` o clone falha, e o adapter (corretamente) reporta que não rodou. Com um
    commit eles enxergam a árvore inteira, que é o que foi enviado. O histórico antigo
    não veio, e isso vira lacuna declarada no relatório, não silêncio.
    """
    git = [
        "git",
        "-c",
        "user.name=roqueshield",
        "-c",
        "user.email=codigo@roqueshield.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "init.defaultBranch=main",
    ]
    if (raiz / ".git").exists():
        raise CodigoRecusado("o envio não pode trazer uma pasta .git")
    for argv in (
        [*git, "init", "-q", str(raiz)],
        [*git, "-C", str(raiz), "add", "-A", "-f"],
        [*git, "-C", str(raiz), "commit", "-q", "--no-verify", "-m", "codigo enviado"],
    ):
        r = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
        if r.returncode != 0:
            raise CodigoRecusado(f"não consegui preparar o repositório: {r.stderr.strip()}")


LACUNA_SEM_HISTORICO = (
    "Código enviado como árvore, sem o histórico git: os scanners de segredo viram só o "
    "estado atual dos arquivos. Segredo que foi commitado e depois apagado não aparece "
    "aqui; para isso, escaneie o repositório pela URL."
)


def _commit_da_fotografia(raiz: Path) -> str | None:
    r = subprocess.run(  # noqa: S603
        ["git", "-C", str(raiz), "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and len(sha) >= 40 else None


def reescrever_alvo(findings: list[Finding], raiz: Path, alvo: Target) -> list[Finding]:
    """Troca o caminho temporário pelo alvo lógico e recalcula a chave de cada achado.

    O commit da fotografia também sai da identidade. O gitleaks usa como discriminador
    o `Fingerprint`, que começa pelo hash do commit (`<commit>:<arquivo>:<regra>:<linha>`);
    cada envio gera um commit novo, então o mesmo segredo no mesmo lugar teria chave
    nova a cada scan e o gate o chamaria de novo para sempre. Medido no teste ponta a
    ponta: 5 de 5 achados do gitleaks "novos" no reenvio do mesmo código.
    """
    prefixo = str(raiz).rstrip("/")
    sha = _commit_da_fotografia(raiz) if (raiz / ".git").exists() else None
    novos: list[Finding] = []
    for f in findings:
        valor = f.target.value
        if valor == prefixo:
            valor = alvo.value
        elif valor.startswith(prefixo + "/"):
            valor = alvo.value + valor[len(prefixo) :]
        dados = f.model_dump()
        dados["target"] = {**dados["target"], "value": valor}
        dados["deduped_key"] = ""
        disc = dados.get("dedup_discriminator")
        if sha and isinstance(disc, str) and sha in disc:
            dados["dedup_discriminator"] = disc.replace(sha + ":", "").replace(sha, "")
        # O caminho do servidor também aparece no texto (título, descrição, evidência):
        # não é segredo, mas é ruído que muda a cada envio e não diz nada a quem lê.
        for campo in ("title", "description"):
            if isinstance(dados.get(campo), str):
                dados[campo] = dados[campo].replace(prefixo, alvo.value)
        for ev in dados.get("evidence") or []:
            for campo in ("description", "request", "response", "payload", "snippet"):
                texto = ev.get(campo)
                if isinstance(texto, str) and prefixo in texto:
                    ev[campo] = texto.replace(prefixo, alvo.value)
        novos.append(Finding.model_validate(dados))
    return novos
