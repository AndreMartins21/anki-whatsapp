"""Testes do export para o Anki (seção 7.3). O arquivo esperado é versionado em
`tests/fixtures/` e comparado byte a byte."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app.domain.models import Entry, Sentence, SentidoSalvo
from app.repo.memory import MemoryRepository
from app.services.anki import ExportadorAnki, escolher_frase
from app.services.storage import ArmazenamentoEmMemoria
from tests.helpers import T0, Relogio

FIXTURES = Path(__file__).parent / "fixtures"
NOME_DO_ARQUIVO = "exports/anki_2026-09-20_1200.txt"


def _entrada(
    palavra: str,
    *,
    classe: str,
    traducao: str,
    definicao: str,
    minutos: int,
    nota: str = "",
    tags: list[str] | None = None,
    exportado: bool = False,
) -> Entry:
    quando = T0 + timedelta(minutes=minutos)
    return Entry(
        slug=palavra.replace(" ", "-"),
        palavra=palavra,
        classe=classe,
        cefr_estimado="B2",
        sentido=SentidoSalvo(traducao=traducao, definicao=definicao),
        nota=nota,
        tags=tags or [],
        exportado=exportado,
        criado_em=quando,
        atualizado_em=quando,
    )


def _frase(texto: str, minutos: int, **campos: object) -> Sentence:
    autor = "bot" if campos.pop("bot", False) else "usuario"
    return Sentence(
        texto=texto,
        autor=autor,
        criado_em=T0 + timedelta(minutes=minutos),
        **campos,
    )


def _repositorio() -> MemoryRepository:
    repo = MemoryRepository()
    repo.criar_entrada(
        _entrada(
            "stall",
            classe="verbo",
            traducao="travar, emperrar",
            definicao="to stop making progress",
            nota='"the car stalled" = o carro morreu',
            tags=["trabalho"],
            minutos=0,
        )
    )
    repo.adicionar_frase(
        "stall",
        _frase(
            "The project stalled because the client didn't sent the documents.",
            1,
            veredito="quase",
            versao_natural="The project [[stalled]] because the client didn't send the documents.",
        ),
    )
    repo.adicionar_frase(
        "stall",
        _frase(
            "The negotiations stalled after the first meeting.",
            2,
            veredito="correta",
            versao_natural="The negotiations [[stalled]] after the first meeting.",
        ),
    )
    repo.adicionar_frase("stall", _frase("The talks [[stalled]] again.", 3, bot=True))

    repo.criar_entrada(
        _entrada(
            "done",
            classe="adjetivo",
            traducao="pronto",
            definicao="finished",
            minutos=5,
            exportado=True,
        )
    )
    repo.adicionar_frase("done", _frase("It is [[done]].", 5, bot=True))

    repo.criar_entrada(
        _entrada(
            "give up",
            classe="phrasal verb",
            traducao="desistir",
            definicao="to stop trying",
            tags=["phrasal_verb"],
            minutos=10,
        )
    )
    repo.adicionar_frase(
        "give-up",
        _frase(
            "He gave up to smoke last year.",
            11,
            veredito="quase",
            versao_natural="He [[gave up]] smoking last year.",
        ),
    )

    repo.criar_entrada(
        _entrada(
            "hedge",
            classe="verbo",
            traducao="se proteger",
            definicao="to protect yourself & reduce risk",
            nota="Line1\nLine2\tx",
            minutos=20,
        )
    )
    repo.adicionar_frase("hedge", _frase("We should [[hedge]] our <bets>.", 21, bot=True))

    repo.criar_entrada(
        _entrada("orphan", classe="verbo", traducao="órfã", definicao="sem frase", minutos=30)
    )
    return repo


def _exportador(repo: MemoryRepository) -> tuple[ExportadorAnki, ArmazenamentoEmMemoria]:
    armazenamento = ArmazenamentoEmMemoria()
    return ExportadorAnki(repo, armazenamento, agora=Relogio().agora), armazenamento


def test_arquivo_bate_byte_a_byte_com_o_esperado() -> None:
    exportador, armazenamento = _exportador(_repositorio())

    exportador.exportar(tudo=False)

    esperado = (FIXTURES / "export_esperado.txt").read_bytes()
    assert armazenamento.arquivos[NOME_DO_ARQUIVO] == esperado


def test_exportar_tudo_inclui_as_ja_exportadas() -> None:
    exportador, armazenamento = _exportador(_repositorio())

    resultado = exportador.exportar(tudo=True)

    esperado = (FIXTURES / "export_esperado_tudo.txt").read_bytes()
    assert armazenamento.arquivos[NOME_DO_ARQUIVO] == esperado
    assert resultado is not None
    assert resultado.quantidade == 4


def test_resultado_traz_o_link_a_quantidade_e_as_ignoradas() -> None:
    exportador, _ = _exportador(_repositorio())

    resultado = exportador.exportar(tudo=False)

    assert resultado is not None
    assert resultado.link == f"memoria://{NOME_DO_ARQUIVO}"
    assert resultado.quantidade == 3
    assert resultado.ignoradas == 1  # "orphan", sem frase nenhuma


def test_exportadas_ficam_marcadas_e_nao_saem_de_novo() -> None:
    repo = _repositorio()
    exportador, armazenamento = _exportador(repo)
    exportador.exportar(tudo=False)

    entrada = repo.obter_entrada("stall")
    assert entrada is not None
    assert entrada.exportado is True
    assert repo.obter_entrada("orphan").exportado is False  # type: ignore[union-attr]

    armazenamento.arquivos.clear()
    assert exportador.exportar(tudo=False) is None
    assert armazenamento.arquivos == {}


def test_sem_nada_para_exportar_devolve_none_e_nao_gera_arquivo() -> None:
    exportador, armazenamento = _exportador(MemoryRepository())

    assert exportador.exportar(tudo=False) is None
    assert armazenamento.arquivos == {}


def test_arquivo_e_utf8_sem_bom_e_termina_em_quebra_de_linha() -> None:
    exportador, armazenamento = _exportador(_repositorio())
    exportador.exportar(tudo=False)

    dados = armazenamento.arquivos[NOME_DO_ARQUIVO]

    assert not dados.startswith(b"\xef\xbb\xbf")
    assert dados.endswith(b"\n")
    assert b"\r" not in dados
    assert "Inglês – Vocabulário".encode() in dados  # o travessão é U+2013


# ---- escolha da frase do cartão (seção 7.2) ---------------------------------------------------


def test_frase_do_cartao_prefere_a_correta_do_usuario_e_marca_o_alvo() -> None:
    entrada = _entrada("stall", classe="verbo", traducao="t", definicao="d", minutos=0)
    frases = [
        _frase("bad one", 1, veredito="quase", versao_natural="A [[stall]]."),
        _frase("The deal stalled.", 2, veredito="correta", versao_natural="The deal [[stalled]]."),
    ]

    assert escolher_frase(entrada, frases) == "The deal [[stalled]]."


def test_sem_correta_usa_a_versao_natural_mais_recente() -> None:
    entrada = _entrada("stall", classe="verbo", traducao="t", definicao="d", minutos=0)
    frases = [
        _frase("a", 1, veredito="quase", versao_natural="Old [[stall]]."),
        _frase("b", 2, veredito="incorreta", versao_natural="New [[stall]]."),
    ]

    assert escolher_frase(entrada, frases) == "New [[stall]]."


def test_sem_frase_do_usuario_usa_o_primeiro_exemplo_do_bot() -> None:
    entrada = _entrada("stall", classe="verbo", traducao="t", definicao="d", minutos=0)
    frases = [
        _frase("First [[stall]].", 1, bot=True),
        _frase("Second [[stall]].", 2, bot=True),
    ]

    assert escolher_frase(entrada, frases) == "First [[stall]]."


def test_sem_nenhuma_frase_devolve_none() -> None:
    entrada = _entrada("stall", classe="verbo", traducao="t", definicao="d", minutos=0)

    assert escolher_frase(entrada, []) is None


def test_frase_correta_sem_o_alvo_reconhecivel_cai_na_versao_natural() -> None:
    entrada = _entrada("give", classe="verbo", traducao="t", definicao="d", minutos=0)
    frases = [_frase("He gave it.", 1, veredito="correta", versao_natural="He [[gave]] it.")]

    assert escolher_frase(entrada, frases) == "He [[gave]] it."


def test_falha_no_armazenamento_nao_marca_nada_como_exportado() -> None:
    class ArmazenamentoQuebrado:
        def enviar(self, nome: str, conteudo: bytes) -> str:
            raise ConnectionError("Storage fora do ar")

    repo = _repositorio()
    exportador = ExportadorAnki(repo, ArmazenamentoQuebrado(), agora=Relogio().agora)

    with pytest.raises(ConnectionError):
        exportador.exportar(tudo=False)

    assert [e.slug for e in repo.listar_entradas() if e.exportado] == ["done"]  # como já era
