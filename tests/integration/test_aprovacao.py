"""Aprovação humana por comando (Frente E).

As invariantes da trava, cada uma com seu teste de mutação: tempo limite NEGA (fecha
fechado), quatro olhos barra quem propôs, decisão é única. E a permissão `commands:approve`
é só do ADMIN.
"""

from __future__ import annotations

import uuid

import pytest

from orchestrator.approvals import service
from orchestrator.config import settings
from orchestrator.domain.roles import Permission, Role, has_permission
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import CommandApprovalRow, CommandApprovalStatus


async def _criar(command: str = "nmap -sV alvo.test", proposed_by: str = "op@x") -> uuid.UUID:
    async with session() as s:
        row = await service.criar_pendencia(s, command=command, proposed_by=proposed_by)
        return row.id


async def test_aprovar_libera_e_negar_barra() -> None:
    await init_db()
    aid = await _criar()
    async with session() as s:
        assert await service.esta_aprovado(s, aid) is False  # pending ainda não libera
        await service.decidir(s, aid, aprovar=True, decided_by="adm@x")
        assert await service.esta_aprovado(s, aid) is True

    bid = await _criar()
    async with session() as s:
        await service.decidir(s, bid, aprovar=False, decided_by="adm@x")
        assert await service.esta_aprovado(s, bid) is False


async def test_tempo_limite_nega(monkeypatch) -> None:
    await init_db()
    # Pendência já nasce vencida: o tempo limite tem de NEGAR, nunca liberar.
    monkeypatch.setattr(settings, "APPROVAL_TIMEOUT_SECONDS", -1)
    aid = await _criar()
    async with session() as s:
        # esta_aprovado nega E marca expired — o tempo limite fecha fechado sozinho.
        assert await service.esta_aprovado(s, aid) is False
        row = await s.get(CommandApprovalRow, aid)
        assert row is not None
        assert row.status == CommandApprovalStatus.EXPIRED.value

    # E decidir uma pendência vencida (ainda sem ninguém ter lido) também é recusado.
    outra = await _criar()
    async with session() as s:
        with pytest.raises(service.Expirada):
            await service.decidir(s, outra, aprovar=True, decided_by="adm@x")


async def test_quatro_olhos_barra_proponente() -> None:
    await init_db()
    aid = await _criar(proposed_by="mesma@x")
    async with session() as s:
        with pytest.raises(service.QuatroOlhos):
            await service.decidir(s, aid, aprovar=True, decided_by="mesma@x")
    # Outra pessoa aprova normalmente.
    async with session() as s:
        row = await service.decidir(s, aid, aprovar=True, decided_by="outra@x")
        assert row.status == CommandApprovalStatus.APPROVED.value


async def test_decisao_e_unica() -> None:
    await init_db()
    aid = await _criar()
    async with session() as s:
        await service.decidir(s, aid, aprovar=True, decided_by="adm@x")
    async with session() as s:
        with pytest.raises(service.JaDecidida):
            await service.decidir(s, aid, aprovar=False, decided_by="adm@x")


async def test_comando_redigido_na_pendencia() -> None:
    await init_db()
    aid = await _criar(command="curl -u alvo@banco.com.br senha=hunter2 https://x")
    async with session() as s:
        row = await s.get(CommandApprovalRow, aid)
        assert "alvo@banco.com.br" not in row.command
        assert "hunter2" not in row.command


async def test_expiracao_vai_para_a_trilha(monkeypatch) -> None:
    await init_db()
    # Expirar é decisão terminal (nega): tem de deixar rastro, como aprovar/negar.
    monkeypatch.setattr(settings, "APPROVAL_TIMEOUT_SECONDS", -1)
    aid = await _criar()
    async with session() as s:
        await service.esta_aprovado(s, aid)  # dispara a auto-expiração
    async with session() as s:
        from sqlmodel import col, select

        from orchestrator.persistence.models import AuditLogRow

        linhas = (
            await s.exec(
                select(AuditLogRow)
                .where(col(AuditLogRow.action) == "command.expire")
                .where(col(AuditLogRow.resource_id) == aid)
            )
        ).all()
        assert len(linhas) == 1


def test_commands_approve_so_admin() -> None:
    assert has_permission(Role.ADMIN, Permission.COMMANDS_APPROVE) is True
    for papel in (Role.OPERATOR, Role.AUDITOR, Role.VIEWER):
        assert has_permission(papel, Permission.COMMANDS_APPROVE) is False


async def test_corrida_negar_e_aprovar_nao_sobrescreve() -> None:
    # A sessão A lê a pendência (`pending` fica na memória dela); a B nega e comita; a A
    # tenta aprovar com o estado velho. Antes, a A sobrescrevia para `approved`. Agora o
    # UPDATE condicional muda zero linhas e a A perde a corrida.
    await init_db()
    aid = await _criar(proposed_by="op@x")
    async with session() as a:
        # Guardar a referência importa: o mapa de identidade do SQLAlchemy é fraco, e sem ela
        # o objeto é coletado e a A relê o banco (aí não há estado velho e o teste não prova nada).
        visto = await a.get(CommandApprovalRow, aid)
        assert visto is not None and visto.status == CommandApprovalStatus.PENDING.value
        await a.commit()  # solta o lock de leitura; o objeto velho segue no mapa da A
        async with session() as b:
            await service.decidir(b, aid, aprovar=False, decided_by="adm2@x")
        with pytest.raises(service.JaDecidida):
            await service.decidir(a, aid, aprovar=True, decided_by="adm@x")
    async with session() as s:
        row = await s.get(CommandApprovalRow, aid)
        assert row is not None
        assert row.status == CommandApprovalStatus.DENIED.value
        assert await service.esta_aprovado(s, aid) is False


async def test_quatro_olhos_barra_token_de_servico() -> None:
    await init_db()
    aid = await _criar(proposed_by="op@x")
    async with session() as s:
        with pytest.raises(service.QuatroOlhos):
            await service.decidir(
                s, aid, aprovar=True, decided_by="service@local", decided_by_is_service=True
            )
    # Negar continua permitido ao serviço: barrar é o lado seguro.
    async with session() as s:
        row = await service.decidir(
            s, aid, aprovar=False, decided_by="service@local", decided_by_is_service=True
        )
        assert row.status == CommandApprovalStatus.DENIED.value


async def test_quatro_olhos_barra_pendencia_sem_propositor() -> None:
    await init_db()
    async with session() as s:
        row = await service.criar_pendencia(s, command="nmap -sV alvo.test", proposed_by=None)
        aid = row.id
    async with session() as s:
        with pytest.raises(service.QuatroOlhos):
            await service.decidir(s, aid, aprovar=True, decided_by="adm@x")


async def test_quatro_olhos_ignora_caixa_do_email() -> None:
    await init_db()
    aid = await _criar(proposed_by="Mesma@X")
    async with session() as s:
        with pytest.raises(service.QuatroOlhos):
            await service.decidir(s, aid, aprovar=True, decided_by="mesma@x")
