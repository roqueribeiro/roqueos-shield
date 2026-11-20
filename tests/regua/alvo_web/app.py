"""Alvo DAST da régua: uma aplicação web com defeitos conhecidos em caminhos fixos.

VULNERÁVEL DE PROPÓSITO, como um DVWA, mas pequena e determinística: cada defeito tem
um caminho, uma CWE e um item no gabarito (tests/regua/gabaritos/alvo_web.yaml), e cada
controle limpo é o mesmo recurso feito do jeito certo. Só a biblioteca padrão, para
subir em qualquer Python sem instalar nada.

NUNCA exponha fora de uma rede de laboratório. A injeção de comando é SIMULADA (a
resposta imita a saída de `cat /etc/passwd` quando o payload pede), para o scanner ter o
que achar sem o processo executar nada de quem ataca.

    python tests/regua/alvo_web/app.py --porta 8088
"""

from __future__ import annotations

import argparse
import html
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PUBLICO = Path(__file__).with_name("publico")

_PAGINA = """<!doctype html><html><head><title>Loja da Régua</title></head><body>
<h1>Loja da Régua</h1>
<ul>
<li><a href="/busca?q=caneca">Busca</a></li>
<li><a href="/busca-segura?q=caneca">Busca segura</a></li>
<li><a href="/produto?id=1">Produto</a></li>
<li><a href="/produto-seguro?id=1">Produto (seguro)</a></li>
<li><a href="/ir?url=/">Ir para</a></li>
<li><a href="/arquivo?nome=manual.txt">Manual</a></li>
<li><a href="/ping?host=127.0.0.1">Ping</a></li>
<li><a href="/entrar">Entrar</a></li>
</ul>
<form action="/busca" method="get"><input name="q"><button>Buscar</button></form>
<form action="/produto" method="get"><input name="id"><button>Ver</button></form>
<form action="/ping" method="get"><input name="host"><button>Ping</button></form>
</body></html>"""

_PASSWD = "root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
# Credenciais FALSAS, no formato de um .env de Laravel/Node exposto por engano.
_ENV = (
    "APP_ENV=production\nAPP_KEY=base64:"
    + "QUJD" * 11
    + "\nDB_HOST=db\nDB_PASSWORD="
    + "senha"
    + "-de-teste\n"
)
_GIT_CONFIG = """[core]
\trepositoryformatversion = 0
\tfilemode = true
\tbare = false
[remote "origin"]
\turl = https://git.exemplo.invalid/loja/loja.git
\tfetch = +refs/heads/*:refs/remotes/origin/*
"""


def _banco() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute("CREATE TABLE produtos (id INTEGER PRIMARY KEY, nome TEXT, preco REAL)")
    db.executemany(
        "INSERT INTO produtos VALUES (?, ?, ?)",
        [(1, "Caneca", 39.9), (2, "Camiseta", 79.9), (3, "Adesivo", 5.0)],
    )
    return db


DB = _banco()


class Alvo(BaseHTTPRequestHandler):
    server_version = "LojaDaRegua/1.0"

    def log_message(self, fmt: str, *args: object) -> None:  # silêncio no CI
        return

    def _responder(
        self, corpo: str, status: int = 200, tipo: str = "text/html; charset=utf-8", **cab: str
    ) -> None:
        dados = corpo.encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        for k, v in cab.items():
            self.send_header(k.replace("_", "-"), v)
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self) -> None:  # noqa: N802 - nome da API do http.server
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        rota = {
            "/": lambda: self._responder(_PAGINA),
            "/busca": lambda: self._busca(q.get("q", ""), seguro=False),
            "/busca-segura": lambda: self._busca(q.get("q", ""), seguro=True),
            "/produto": lambda: self._produto(q.get("id", "1"), seguro=False),
            "/produto-seguro": lambda: self._produto(q.get("id", "1"), seguro=True),
            "/ir": lambda: self._responder("", 302, Location=q.get("url", "/")),
            "/arquivo": lambda: self._arquivo(q.get("nome", "manual.txt")),
            "/ping": lambda: self._ping(q.get("host", "127.0.0.1")),
            "/entrar": self._entrar,
            "/.git/config": lambda: self._responder(_GIT_CONFIG, tipo="text/plain"),
            "/.env": lambda: self._responder(_ENV, tipo="text/plain"),
            "/robots.txt": lambda: self._responder("User-agent: *\nDisallow:\n", tipo="text/plain"),
        }.get(u.path)
        if rota is None:
            self._responder("<h1>404</h1>", 404)
            return
        rota()

    # ---- defeitos e os controles limpos correspondentes -------------------------

    def _busca(self, termo: str, *, seguro: bool) -> None:
        # CWE-79: o termo volta na página sem escapar. A versão segura escapa.
        mostrado = html.escape(termo) if seguro else termo
        self._responder(f"<html><body><p>Resultados para: {mostrado}</p></body></html>")

    def _produto(self, ident: str, *, seguro: bool) -> None:
        # CWE-89: o id entra no SQL por concatenação, e o erro do banco vai para a página.
        try:
            if seguro:
                linhas = DB.execute("SELECT nome, preco FROM produtos WHERE id = ?", (ident,))
            else:
                linhas = DB.execute(f"SELECT nome, preco FROM produtos WHERE id = {ident}")  # noqa: S608
            itens = "".join(f"<li>{html.escape(str(n))}: {p}</li>" for n, p in linhas)
            self._responder(f"<html><body><ul>{itens}</ul></body></html>")
        except sqlite3.Error as e:
            if seguro:
                self._responder("<p>produto inválido</p>", 400)
            else:
                self._responder(f"<p>Erro no banco: sqlite3.OperationalError: {e}</p>", 500)

    def _arquivo(self, nome: str) -> None:
        # CWE-22: o nome entra no caminho sem normalizar. Arquivos de sistema são
        # simulados (nada fora de `publico/` é lido de verdade).
        # Resolve como um sistema de arquivos de verdade: só `../../etc/passwd` ou
        # `/etc/passwd` chegam lá. A sonda de injeção de COMANDO (`;cat /etc/passwd`,
        # quebra de linha + `cat /etc/passwd`) não é caminho válido, e responder a ela
        # faria o scanner ver uma injeção de comando que esta rota não tem (medido: o ZAP
        # acusou CWE-78 aqui).
        if os.path.normpath(os.path.join("/srv/publico", nome)) == "/etc/passwd":
            self._responder(_PASSWD, tipo="text/plain")
            return
        alvo = PUBLICO / nome
        if alvo.is_file():
            self._responder(alvo.read_text(encoding="utf-8"), tipo="text/plain")
        else:
            self._responder("não encontrado", 404, tipo="text/plain")

    def _ping(self, host: str) -> None:
        # CWE-78 SIMULADA: um app real faria `sh -c "ping -c 1 " + host`. Aqui nada roda:
        # o metacaractere de shell seguido de um comando de leitura devolve o que o shell
        # devolveria, que é o que o scanner procura.
        saida = "PING 127.0.0.1: 56 data bytes\n64 bytes from 127.0.0.1: icmp_seq=0\n"
        if any(m in host for m in (";", "|", "&", "`", "$(")) and "passwd" in host:
            saida += _PASSWD
        self._responder(f"<pre>{html.escape(saida)}</pre>")

    def _entrar(self) -> None:
        # CWE-1004 / CWE-614: cookie de sessão sem HttpOnly e sem Secure.
        self._responder(
            "<form method=post><input name=usuario><input type=password name=senha></form>",
            Set_Cookie="sessao=abc123def456; Path=/",
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 - alvo de laboratório
    p.add_argument("--porta", type=int, default=8088)
    a = p.parse_args()
    ThreadingHTTPServer((a.host, a.porta), Alvo).serve_forever()


if __name__ == "__main__":
    main()
