"""GOAL-SHIELD-02 (Issue #13): o que entrou no lugar das dependências vulneráveis.

- `python-libnmap` (CVE-2022-30284, XXE) -> parser próprio com `defusedxml`.
- `python-jose` (CVE-2024-33663/33664, parado) -> PyJWT >= 2.14.

Os testes provam o comportamento que o CVE quebrava, não só que o import mudou: um
XML de nmap com entidade externa não lê arquivo nenhum, e um JWT com `alg` trocado
não passa.
"""

from __future__ import annotations

import time
from uuid import uuid4

import jwt
import pytest

from orchestrator.adapters._nmap_xml import NmapXmlError, parse_nmap_xml
from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.adapters.nmap_adapter import NmapAdapter
from orchestrator.auth import session as sessao
from orchestrator.domain.schemas import RawResults

# Cabeçalho como o nmap escreve de verdade: tem DOCTYPE, sem entidade.
_NMAP = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun scanner="nmap" args="nmap -sV -oX - 10.0.0.5" version="7.95">
  <host>
    <status state="up"/>
    <address addr="aa:bb:cc:dd:ee:ff" addrtype="mac"/>
    <address addr="10.0.0.5" addrtype="ipv4"/>
    <hostnames><hostname name="srv.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open"/>
        <service name="ssh" product="OpenSSH" version="9.6p1" extrainfo="Ubuntu"/></port>
      <port protocol="tcp" portid="23"><state state="open"/><service name="telnet"/></port>
      <port protocol="tcp" portid="80"><state state="closed"/><service name="http"/></port>
      <port protocol="udp" portid="161"><state state="open"/></port>
    </ports>
  </host>
</nmaprun>"""


def test_le_o_relatorio_do_nmap_com_doctype_enderecos_nomes_e_banner():
    [host] = parse_nmap_xml(_NMAP)
    assert host.address == "10.0.0.5"  # IPv4 antes do MAC, como o libnmap
    assert host.hostnames == ["srv.local"]
    assert [(s.port, s.protocol, s.state, s.service, s.banner) for s in host.services] == [
        (22, "tcp", "open", "ssh", "OpenSSH 9.6p1 Ubuntu"),
        (23, "tcp", "open", "telnet", ""),
        (80, "tcp", "closed", "http", ""),
        (161, "udp", "open", "", ""),
    ]


@pytest.mark.parametrize(
    "xml",
    [
        # CVE-2022-30284: entidade externa lendo arquivo local
        '<?xml version="1.0"?><!DOCTYPE nmaprun [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        '<nmaprun><host><address addr="&x;" addrtype="ipv4"/></host></nmaprun>',
        # billion laughs
        '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<nmaprun><host><hostnames><hostname name='&b;'/></hostnames></host></nmaprun>",
        # nmap morto no meio (XML truncado)
        '<?xml version="1.0"?><nmaprun><host><address addr="10.0.0.5"',
        # outro formato
        "<relatorio/>",
        # porta que não é número
        '<nmaprun><host><ports><port protocol="tcp" portid="x"/></ports></host></nmaprun>',
    ],
    ids=["xxe", "billion-laughs", "truncado", "outra-raiz", "porta-ilegivel"],
)
def test_xml_adulterado_ou_ilegivel_e_recusado(xml):
    with pytest.raises(NmapXmlError):
        parse_nmap_xml(xml)


async def test_adapter_normaliza_portas_abertas_e_recusa_xml_com_entidade():
    adapter = NmapAdapter.__new__(NmapAdapter)
    achados = await adapter.normalize(RawResults(adapter="nmap", payload=_NMAP))
    assert sorted(f.target.value for f in achados) == [
        "10.0.0.5:161/udp",
        "10.0.0.5:22/tcp",
        "10.0.0.5:23/tcp",
    ]
    ssh = next(f for f in achados if f.target.value.endswith("22/tcp"))
    assert "OpenSSH 9.6p1 Ubuntu" in ssh.description

    xxe = (
        '<?xml version="1.0"?><!DOCTYPE nmaprun [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        '<nmaprun><host><address addr="&x;" addrtype="ipv4"/></host></nmaprun>'
    )
    with pytest.raises(ScanIntegrityError, match="XML ilegível"):
        await adapter.normalize(RawResults(adapter="nmap", payload=xxe))


@pytest.fixture
def chave(monkeypatch):
    monkeypatch.setattr(sessao.settings, "SESSION_SECRET", "segredo-de-teste-com-32-bytes!!!")
    return "segredo-de-teste-com-32-bytes!!!"


def test_sessao_emitida_volta_com_os_claims(chave):
    uid = uuid4()
    claims = sessao.verify_session(sessao.issue_session(user_id=uid, email="a@b.c", role="viewer"))
    assert {k: claims[k] for k in ("sub", "email", "role", "typ")} == {
        "sub": str(uid),
        "email": "a@b.c",
        "role": "viewer",
        "typ": "session",
    }


def test_sessao_adulterada_expirada_ou_com_outro_alg_nao_passa(chave):
    agora = int(time.time())
    base = {"sub": "u1", "typ": "session", "iat": agora, "exp": agora + 60}
    valido = jwt.encode(base, chave, algorithm="HS256")
    cabecalho, corpo, assinatura = valido.split(".")
    casos = {
        "assinatura trocada": f"{cabecalho}.{corpo}.{assinatura[::-1]}",
        "expirado": jwt.encode({**base, "exp": agora - 1}, chave, algorithm="HS256"),
        "alg none": jwt.encode(base, None, algorithm="none"),
        "outro HMAC": jwt.encode(base, chave, algorithm="HS512"),
        "sem exp": jwt.encode({k: v for k, v in base.items() if k != "exp"}, chave, "HS256"),
        "typ errado": jwt.encode({**base, "typ": "refresh"}, chave, algorithm="HS256"),
        "outra chave": jwt.encode(base, "outra-chave-bem-comprida-32-bytes", "HS256"),
    }
    assert {nome: sessao.verify_session(tok) for nome, tok in casos.items()} == dict.fromkeys(casos)
    assert sessao.verify_session(valido)["sub"] == "u1"
    assert sessao.verify_session("") is None
