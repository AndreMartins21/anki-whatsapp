"""Teste de contrato do `Repository` (seção 7.1): o mesmo teste vale para todas as implementações.

`MemoryRepository` sempre roda. `FirestoreRepository` só roda contra o emulador
(`FIRESTORE_EMULATOR_HOST` definido) — nunca contra o Firestore de verdade (ADR-0003).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.domain.models import (
    Entry,
    Estado,
    Profile,
    Sentence,
    SentidoSalvo,
    Sessao,
)
from app.repo.base import EntradaJaExiste, Repository, resolver_slug
from app.repo.memory import MemoryRepository

T0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
PROJETO_TESTE = "vocabot-teste"


def _entrada(
    palavra: str = "stall", *, traducao: str = "travar", criado_em: datetime = T0
) -> Entry:
    return Entry(
        slug=palavra,
        palavra=palavra,
        classe="verb",
        cefr_estimado="B2",
        sentido=SentidoSalvo(traducao=traducao, definicao="to stop making progress"),
        outros_sentidos=[SentidoSalvo(traducao="enrolar", definicao="to delay")],
        nota="phrasal em contexto de trabalho",
        tags=["trabalho"],
        origem_texto="stall | the talks stalled",
        criado_em=criado_em,
        atualizado_em=criado_em,
    )


@pytest.fixture(params=["memory", "firestore"])
def repo(request: pytest.FixtureRequest) -> Iterator[Repository]:
    if request.param == "memory":
        yield MemoryRepository()
        return

    host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not host:
        pytest.skip("FIRESTORE_EMULATOR_HOST não definido (emulador do Firestore não está rodando)")

    from google.cloud import firestore

    from app.repo.firestore import FirestoreRepository

    limpar = f"http://{host}/emulator/v1/projects/{PROJETO_TESTE}/databases/(default)/documents"
    httpx.delete(limpar)
    yield FirestoreRepository(firestore.Client(project=PROJETO_TESTE))
    httpx.delete(limpar)


def test_perfil_ausente_e_none_e_depois_persiste(repo: Repository) -> None:
    assert repo.obter_perfil() is None

    repo.salvar_perfil(Profile(nivel="B1-B2", criado_em=T0))

    assert repo.obter_perfil() == Profile(nivel="B1-B2", criado_em=T0)


def test_sessao_ausente_comeca_em_idle(repo: Repository) -> None:
    sessao = repo.obter_sessao()

    assert sessao.estado == Estado.IDLE
    assert sessao.entry_id is None


def test_sessao_persiste_estado_e_sinonimos_mostrados(repo: Repository) -> None:
    sessao = Sessao(
        estado=Estado.AWAIT_ACTION,
        entry_id="stall",
        sentido_id="s1",
        sinonimos_mostrados=["stumble", "grind to a halt"],
        atualizado_em=T0,
    )

    repo.salvar_sessao(sessao)

    assert repo.obter_sessao() == sessao


def test_sessao_persiste_a_fila_de_revisao(repo: Repository) -> None:
    sessao = Sessao(
        estado=Estado.REVIEWING,
        revisao_fila=["hedge", "deadline"],
        revisao_atual="stall",
        revisao_feitas=["reluctant"],
        revisao_lapsos=["reluctant"],
        revisao_total=4,
        atualizado_em=T0,
    )

    repo.salvar_sessao(sessao)

    assert repo.obter_sessao() == sessao


def test_perfil_persiste_os_campos_de_lembretes(repo: Repository) -> None:
    perfil = Profile(
        nivel="B1-B2",
        criado_em=T0,
        lembretes_por_dia=3,
        janela_inicio=9,
        janela_fim=22,
        chat_id="5531999998888@c.us",
        proximo_lembrete=T0 + timedelta(hours=3),
        lembrete_sem_resposta=True,
        avisou_lembretes=True,
    )

    repo.salvar_perfil(perfil)

    assert repo.obter_perfil() == perfil


def test_entrada_criada_pode_ser_lida(repo: Repository) -> None:
    repo.criar_entrada(_entrada())

    assert repo.obter_entrada("stall") == _entrada()
    assert repo.obter_entrada("outra") is None


def test_entrada_persiste_os_campos_de_revisao_espacada(repo: Repository) -> None:
    entrada = _entrada().model_copy(
        update={
            "repeticoes": 3,
            "intervalo_dias": 7.5,
            "facilidade": 2.3,
            "lapsos": 1,
            "proxima_revisao": T0 + timedelta(days=7),
            "revisada_em": T0,
        }
    )
    repo.criar_entrada(entrada)

    assert repo.obter_entrada("stall") == entrada


def test_criar_entrada_com_slug_existente_falha_sem_sobrescrever(repo: Repository) -> None:
    repo.criar_entrada(_entrada())

    with pytest.raises(EntradaJaExiste):
        repo.criar_entrada(_entrada(traducao="outra coisa"))

    entrada = repo.obter_entrada("stall")
    assert entrada is not None
    assert entrada.sentido.traducao == "travar"


def test_salvar_entrada_atualiza(repo: Repository) -> None:
    repo.criar_entrada(_entrada())
    atualizada = _entrada().model_copy(update={"status": "praticada", "exportado": True})

    repo.salvar_entrada(atualizada)

    assert repo.obter_entrada("stall") == atualizada


def test_listar_entradas_em_ordem_de_criacao_e_filtra_por_status(repo: Repository) -> None:
    repo.criar_entrada(_entrada("beta", criado_em=T0 + timedelta(minutes=2)))
    repo.criar_entrada(_entrada("alfa", criado_em=T0 + timedelta(minutes=1)))
    repo.criar_entrada(
        _entrada("gama", criado_em=T0 + timedelta(minutes=3)).model_copy(
            update={"status": "praticada"}
        )
    )

    todas = [e.slug for e in repo.listar_entradas()]
    novas = [e.slug for e in repo.listar_entradas("nova")]
    praticadas = [e.slug for e in repo.listar_entradas("praticada")]

    assert todas == ["alfa", "beta", "gama"]
    assert novas == ["alfa", "beta"]
    assert praticadas == ["gama"]


def test_frases_sao_guardadas_por_entrada_em_ordem(repo: Repository) -> None:
    repo.criar_entrada(_entrada())
    segunda = Sentence(texto="segunda", autor="usuario", criado_em=T0 + timedelta(minutes=1))
    primeira = Sentence(
        texto="primeira",
        autor="usuario",
        veredito="quase",
        correcoes=["didn't sent → didn't send"],
        versao_natural="The project [[stalled]].",
        explicacao="Depois de didn't, o verbo fica na forma base.",
        criado_em=T0,
    )

    repo.adicionar_frase("stall", segunda)
    repo.adicionar_frase("stall", primeira)

    assert repo.listar_frases("stall") == [primeira, segunda]
    assert repo.listar_frases("outra") == []


def test_apagar_entrada_remove_tambem_as_frases(repo: Repository) -> None:
    repo.criar_entrada(_entrada())
    repo.adicionar_frase("stall", Sentence(texto="x", autor="bot", criado_em=T0))

    assert repo.apagar_entrada("stall") is True

    assert repo.obter_entrada("stall") is None
    assert repo.listar_frases("stall") == []
    assert repo.apagar_entrada("stall") is False


def test_mensagem_so_e_marcada_como_processada_uma_vez(repo: Repository) -> None:
    assert repo.marcar_processada("true_5531@c.us_ABC", T0) is True
    assert repo.marcar_processada("true_5531@c.us_ABC", T0) is False
    assert repo.marcar_processada("true_5531@c.us_OUTRA", T0) is True


def test_cache_de_lid(repo: Repository) -> None:
    assert repo.obter_numero_do_lid("257161284317237@lid") is None

    repo.salvar_numero_do_lid("257161284317237@lid", "5531999998888")

    assert repo.obter_numero_do_lid("257161284317237@lid") == "5531999998888"


def test_resolver_slug_usa_a_palavra_quando_esta_livre(repo: Repository) -> None:
    assert resolver_slug(repo, "Stall", "travar") == "stall"
    assert resolver_slug(repo, "give up", "desistir") == "give-up"


def test_resolver_slug_reaproveita_o_slug_do_mesmo_sentido(repo: Repository) -> None:
    repo.criar_entrada(_entrada())

    assert resolver_slug(repo, "stall", "travar") == "stall"


def test_resolver_slug_sufixa_quando_o_sentido_e_outro(repo: Repository) -> None:
    repo.criar_entrada(_entrada())

    assert resolver_slug(repo, "stall", "barraca") == "stall--s2"

    repo.criar_entrada(
        _entrada().model_copy(
            update={
                "slug": "stall--s2",
                "sentido": SentidoSalvo(traducao="barraca", definicao="a stand"),
            }
        )
    )

    assert resolver_slug(repo, "stall", "barraca") == "stall--s2"
    assert resolver_slug(repo, "stall", "baia") == "stall--s3"
