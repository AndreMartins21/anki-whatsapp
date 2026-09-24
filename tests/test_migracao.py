"""Migração do formato de um usuário só (raiz do banco) para `espacos/{chat}` (M14, ADR-0017).

Dry run é o padrão e não escreve nada; executar é idempotente (segunda vez não duplica); a origem
só é apagada por `--limpar-origem`, e só com a cópia completa. Roda contra o MemoryRepository — nunca
contra o Firestore real."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.models import Entry, Estado, Profile, Sentence, SentidoSalvo, Sessao
from app.repo.memory import MemoryBanco, MemoryRepository
from scripts.migrar_multiusuario import (
    CopiaIncompleta,
    copia_completa,
    escolher_espaco,
    limpar_origem,
    migrar,
)
from tests.helpers import T0

DONO = "5531999998888@c.us"


def _entrada(slug: str, *, minutos: int = 0, traducao: str = "travar") -> Entry:
    quando = T0 + timedelta(minutes=minutos)
    return Entry(
        slug=slug,
        palavra=slug,
        classe="verb",
        cefr_estimado="B2",
        sentido=SentidoSalvo(traducao=traducao, definicao="to stop"),
        criado_em=quando,
        atualizado_em=quando,
    )


def _frase(texto: str, minutos: int = 0) -> Sentence:
    return Sentence(texto=texto, autor="usuario", criado_em=T0 + timedelta(minutes=minutos))


def _origem() -> MemoryRepository:
    origem = MemoryRepository()
    origem.salvar_perfil(Profile(nivel="B2-C1", chat_id=DONO, lembretes_por_dia=3, criado_em=T0))
    origem.criar_entrada(_entrada("stall"))
    origem.criar_entrada(_entrada("hedge", minutos=1))
    origem.adicionar_frase("stall", _frase("It stalled.", 1))
    origem.adicionar_frase("stall", _frase("Talks stalled.", 2))
    origem.adicionar_frase("hedge", _frase("Don't hedge.", 3))
    return origem


def _destino() -> MemoryRepository:
    destino = MemoryBanco().do_espaco(DONO)
    assert isinstance(destino, MemoryRepository)
    return destino


def test_dry_run_nao_escreve_nada_mas_conta_o_que_faria() -> None:
    origem, destino = _origem(), _destino()

    relatorio = migrar(origem, destino, executar=False)

    assert destino.obter_perfil() is None
    assert destino.listar_entradas() == []
    assert (relatorio.perfil, relatorio.entradas_novas, relatorio.frases_copiadas) == (True, 2, 3)


def test_executar_copia_perfil_entradas_e_frases() -> None:
    origem, destino = _origem(), _destino()
    origem.salvar_sessao(Sessao(estado=Estado.AWAIT_ACTION, entry_id="stall"))

    migrar(origem, destino, executar=True)

    assert destino.obter_perfil() == origem.obter_perfil()
    assert [e.slug for e in destino.listar_entradas()] == ["stall", "hedge"]
    assert [f.texto for f in destino.listar_frases("stall")] == ["It stalled.", "Talks stalled."]
    assert [f.texto for f in destino.listar_frases("hedge")] == ["Don't hedge."]
    assert destino.obter_sessao().estado == Estado.AWAIT_ACTION
    assert copia_completa(origem, destino)


def test_executar_de_novo_nao_duplica_nada() -> None:
    origem, destino = _origem(), _destino()
    migrar(origem, destino, executar=True)

    relatorio = migrar(origem, destino, executar=True)

    assert len(destino.listar_entradas()) == 2
    assert len(destino.listar_frases("stall")) == 2
    assert (
        relatorio.entradas_novas,
        relatorio.entradas_atualizadas,
        relatorio.frases_copiadas,
    ) == (
        0,
        0,
        0,
    )
    assert relatorio.entradas_iguais == 2


def test_segunda_execucao_traz_so_o_que_o_bot_antigo_gravou_na_janela() -> None:
    origem, destino = _origem(), _destino()
    migrar(origem, destino, executar=True)
    # depois da 1ª cópia e antes do deploy, o bot antigo ainda grava na raiz:
    origem.criar_entrada(_entrada("nova", minutos=10))
    origem.salvar_entrada(_entrada("stall", minutos=20, traducao="emperrar"))
    origem.adicionar_frase("stall", _frase("Third one.", 21))

    relatorio = migrar(origem, destino, executar=True)

    assert (relatorio.entradas_novas, relatorio.entradas_atualizadas) == (1, 1)
    assert destino.obter_entrada("stall").sentido.traducao == "emperrar"  # type: ignore[union-attr]
    assert [f.texto for f in destino.listar_frases("stall")] == [
        "It stalled.",
        "Talks stalled.",
        "Third one.",
    ]
    assert copia_completa(origem, destino)


def test_nunca_sobrescreve_uma_entrada_mais_nova_do_destino() -> None:
    origem, destino = _origem(), _destino()
    destino.criar_entrada(_entrada("stall", minutos=99, traducao="do bot novo"))

    migrar(origem, destino, executar=True)

    assert destino.obter_entrada("stall").sentido.traducao == "do bot novo"  # type: ignore[union-attr]


def test_perfil_ja_existente_no_destino_e_mantido() -> None:
    origem, destino = _origem(), _destino()
    destino.salvar_perfil(Profile(nivel="A2-B1", chat_id=DONO, criado_em=T0))

    relatorio = migrar(origem, destino, executar=True)

    perfil = destino.obter_perfil()
    assert perfil is not None and perfil.nivel == "A2-B1"
    assert relatorio.perfil is False


def test_limpar_origem_recusa_com_a_copia_incompleta() -> None:
    origem, destino = _origem(), _destino()
    migrar(origem, destino, executar=True)
    origem.criar_entrada(_entrada("nova", minutos=10))  # ainda não copiada

    with pytest.raises(CopiaIncompleta):
        limpar_origem(origem, destino)

    assert len(origem.listar_entradas()) == 3  # nada foi apagado


def test_limpar_origem_recusa_sem_ter_copiado_nada() -> None:
    origem, destino = _origem(), _destino()

    with pytest.raises(CopiaIncompleta):
        limpar_origem(origem, destino)

    assert origem.obter_perfil() is not None


def test_limpar_origem_apaga_so_a_origem_com_a_copia_completa() -> None:
    origem, destino = _origem(), _destino()
    migrar(origem, destino, executar=True)

    limpar_origem(origem, destino)

    assert origem.obter_perfil() is None
    assert origem.listar_entradas() == []
    assert len(destino.listar_entradas()) == 2
    assert len(destino.listar_frases("stall")) == 2


def test_origem_vazia_e_copia_completa_e_migrar_nao_faz_nada() -> None:
    origem, destino = MemoryRepository(), _destino()

    relatorio = migrar(origem, destino, executar=True)

    assert (relatorio.perfil, relatorio.entradas_novas) == (False, 0)
    assert copia_completa(origem, destino)


def test_espaco_do_dono_vem_do_chat_id_real_do_perfil_antigo() -> None:
    """O WhatsApp pode ter a conta sem o nono dígito: o `chat_id` aprendido é o que vale."""
    origem = MemoryRepository()
    origem.salvar_perfil(Profile(nivel="B1-B2", chat_id="553199998888@c.us", criado_em=T0))

    assert escolher_espaco(origem, espaco=None, dono="5531999998888") == "553199998888@c.us"


def test_espaco_explicito_vence_e_sem_perfil_cai_no_numero_do_dono() -> None:
    origem = MemoryRepository()
    assert escolher_espaco(origem, espaco="1@c.us", dono="5531999998888") == "1@c.us"
    assert escolher_espaco(origem, espaco=None, dono="+55 31 99999-8888") == "5531999998888@c.us"
    with pytest.raises(ValueError, match="dono"):
        escolher_espaco(origem, espaco=None, dono=None)


def test_datas_sao_preservadas_na_copia() -> None:
    origem, destino = _origem(), _destino()
    migrar(origem, destino, executar=True)

    copiada: datetime = destino.obter_entrada("hedge").criado_em  # type: ignore[union-attr]
    assert copiada == T0 + timedelta(minutes=1)


def test_migracao_completa_no_emulador_do_firestore() -> None:
    """Origem no formato antigo (raiz do banco) -> `espacos/{chat}`, no emulador."""
    import os

    import httpx

    host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not host:
        pytest.skip("FIRESTORE_EMULATOR_HOST não definido (emulador do Firestore não está rodando)")

    from google.cloud import firestore

    from app.repo.firestore import FirestoreBanco, FirestoreRepository

    projeto = "vocabot-teste-migracao"
    limpar = f"http://{host}/emulator/v1/projects/{projeto}/databases/(default)/documents"
    httpx.delete(limpar)
    try:
        cliente = firestore.Client(project=projeto)
        origem = FirestoreRepository(cliente)  # o formato antigo: tudo na raiz
        for espelho in [_origem()]:
            perfil = espelho.obter_perfil()
            assert perfil is not None
            origem.salvar_perfil(perfil)
            for e in espelho.listar_entradas():
                origem.criar_entrada(e)
                for f in espelho.listar_frases(e.slug):
                    origem.adicionar_frase(e.slug, f)
        destino = FirestoreBanco(cliente).do_espaco(DONO)

        assert migrar(origem, destino, executar=False).entradas_novas == 2
        assert destino.listar_entradas() == []

        migrar(origem, destino, executar=True)
        segunda = migrar(origem, destino, executar=True)

        assert [e.slug for e in destino.listar_entradas()] == ["stall", "hedge"]
        assert len(destino.listar_frases("stall")) == 2
        assert (segunda.entradas_novas, segunda.frases_copiadas) == (0, 0)
        assert copia_completa(origem, destino)

        limpar_origem(origem, destino)

        assert origem.obter_perfil() is None and origem.listar_entradas() == []
        assert len(destino.listar_entradas()) == 2
    finally:
        httpx.delete(limpar)
