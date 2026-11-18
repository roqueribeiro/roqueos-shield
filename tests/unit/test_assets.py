"""Inventário de ativos — funções puras (Frente A).

A classificação `disappeared` vs `not_verified` é o contrato do silêncio aplicado a
ativo: zero observações com o scanner derrubado não é "a porta fechou", é "ninguém
olhou". Reverter essa distinção (tratar ausência como sumiço sempre) tem de reprovar.
"""

from __future__ import annotations

from orchestrator.domain.assets import asset_key, classificar_presenca


def test_asset_key_estavel_para_o_mesmo_alvo() -> None:
    assert asset_key("port", "10.0.0.1:443/tcp") == asset_key("port", "10.0.0.1:443/tcp")


def test_asset_key_ignora_variacao_trivial() -> None:
    # Barra final e caixa do host não podem criar um ativo "novo" no scan seguinte.
    assert asset_key("url", "https://a.test/x/") == asset_key("url", "https://a.test/x")
    assert asset_key("host", "Example.COM") == asset_key("host", "example.com")


def test_asset_key_dobra_caixa_do_host_na_url() -> None:
    # Caixa do host não distingue ativo (DNS é case-insensitive); o path, sim.
    assert asset_key("url", "https://A.Test/x") == asset_key("url", "https://a.test/x")
    assert asset_key("url", "https://a.test/X") != asset_key("url", "https://a.test/x")


def test_asset_key_distingue_tipo_e_valor() -> None:
    assert asset_key("host", "a.test") != asset_key("domain", "a.test")
    assert asset_key("port", "a.test:80/tcp") != asset_key("port", "a.test:443/tcp")


def test_presenca_present_quando_observado() -> None:
    assert classificar_presenca("port", observado_no_scan=True, scanners_ran=[]) == "present"


def test_presenca_disappeared_quando_quem_ve_rodou() -> None:
    # Porta ausente e o nmap (quem enxerga porta) rodou → sumiu de verdade.
    assert (
        classificar_presenca("port", observado_no_scan=False, scanners_ran=["nmap"])
        == "disappeared"
    )


def test_presenca_not_verified_quando_quem_ve_nao_rodou() -> None:
    # nmap derrubado: a ausência não é "sumiu", é "ninguém olhou".
    assert (
        classificar_presenca("port", observado_no_scan=False, scanners_ran=["zap"])
        == "not_verified"
    )
    assert classificar_presenca("port", observado_no_scan=False, scanners_ran=[]) == "not_verified"
