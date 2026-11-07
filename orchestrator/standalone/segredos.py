"""Segredos do primeiro boot do container standalone.

Quem roda `docker run` sem passar `APP_TOKEN` não deveria ter de inventar um token
forte, e também não pode receber o de exemplo (o boot guard recusa, SEC-01). Então o
container gera os seus, uma vez, em `<DATA_DIR>/secrets/`, com permissão 0600, e os
reaproveita em todo boot seguinte.

O que é passado pelo ambiente vence sempre: um ambiente regulado injeta os próprios
segredos (cofre, Kubernetes secret) e nada é gerado.

Regra que este módulo não quebra: o valor de um segredo nunca vai para log, stdout,
stderr nem mensagem de erro. Só o NOME do segredo e de onde ele veio. O teste
`test_standalone_segredos.py` captura toda a saída e reprova se aparecer um valor.
"""

from __future__ import annotations

import os
import secrets as _rnd
from dataclasses import dataclass
from pathlib import Path

# nome da variável → bytes de entropia. Base64 do Fernet precisa de 32 bytes exatos.
SEGREDOS: dict[str, int] = {
    "APP_TOKEN": 32,
    "SESSION_SECRET": 32,
    "SECRETS_KEY": 32,
    # O ZAP do container escuta só em 127.0.0.1, mas a API dele aceita qualquer
    # processo local: a chave fecha isso para o que não for o worker.
    "ZAP_API_KEY": 24,
    # O Redis do container também escuta só em 127.0.0.1, mas o ZAP do mesmo container
    # processa conteúdo hostil e o arq desserializa job com pickle: senha no Redis.
    "REDIS_PASSWORD": 24,
    # Código de primeiro uso: o POST /setup só cria o primeiro admin com ele. É o que
    # impede quem alcança a porta antes do dono de virar admin.
    "SETUP_CODE": 12,
}


@dataclass(frozen=True)
class Origem:
    nome: str
    de_onde: str  # "ambiente" | "arquivo" | "gerado"


def _gerar(nome: str, n: int) -> str:
    if nome == "SECRETS_KEY":
        import base64

        return base64.urlsafe_b64encode(_rnd.token_bytes(n)).decode("ascii")
    return _rnd.token_hex(n)


def _gravar(caminho: Path, valor: str) -> None:
    # Cria já com 0600: o arquivo nunca existe, nem por um instante, legível por outros.
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(valor)


def garantir(
    pasta: Path, ambiente: dict[str, str] | None = None
) -> tuple[dict[str, str], list[Origem]]:
    """Garante um valor para cada segredo e devolve (valores, origens).

    Ordem: ambiente (não vazio) → arquivo em `pasta` → gera e grava em `pasta`.
    Os valores voltam para quem chamou exportar no ambiente do processo; as origens
    são o que pode ir para o log.
    """
    env = os.environ if ambiente is None else ambiente
    pasta.mkdir(parents=True, exist_ok=True)
    os.chmod(pasta, 0o700)
    valores: dict[str, str] = {}
    origens: list[Origem] = []
    for nome, n in SEGREDOS.items():
        do_ambiente = (env.get(nome) or "").strip()
        if do_ambiente:
            valores[nome] = do_ambiente
            origens.append(Origem(nome, "ambiente"))
            continue
        arq = pasta / nome
        if arq.exists():
            valor = arq.read_text(encoding="utf-8").strip()
            if valor:
                valores[nome] = valor
                origens.append(Origem(nome, "arquivo"))
                continue
            arq.unlink()
        valor = _gerar(nome, n)
        _gravar(arq, valor)
        valores[nome] = valor
        origens.append(Origem(nome, "gerado"))
    return valores, origens


def main() -> None:
    """`python -m orchestrator.standalone.segredos <pasta-envdir>`.

    Usado pelo s6 no boot: garante os segredos e escreve um envdir (um arquivo por
    variável) que os serviços leem com `s6-envdir`. Imprime só nome e origem.
    """
    import sys

    data = Path(os.environ.get("DATA_DIR", "/data"))
    pasta = data / "secrets"
    valores, origens = garantir(pasta)
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if destino is not None:
        destino.mkdir(parents=True, exist_ok=True)
        os.chmod(destino, 0o700)
        for nome, valor in valores.items():
            alvo = destino / nome
            if alvo.exists():
                alvo.unlink()
            _gravar(alvo, valor)
    for o in origens:
        print(f"segredo {o.nome}: {o.de_onde}")


if __name__ == "__main__":
    main()
