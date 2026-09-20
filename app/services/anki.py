"""Export para o Anki (seção 7.3 da spec). O formato é fixo — não mudar.

O tipo de nota "Inglês – Vocabulário" já existe no Anki do aluno, com os campos
`Palavra, Frase, FraseLacuna, Traducao, Definicao, Nota, Producao`. O arquivo é UTF-8, separado
por tab, com HTML ligado e a coluna 8 como tags.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.choices import marcar_alvo
from app.domain.models import Entry, Sentence, agora_utc
from app.repo.base import Repository
from app.services.storage import Armazenamento

CABECALHO = (
    "#separator:tab\n"
    "#html:true\n"
    "#notetype:Inglês – Vocabulário\n"  # o travessão é U+2013
    "#deck:Inglês::Vocabulário\n"
    "#columns:Palavra\tFrase\tFraseLacuna\tTraducao\tDefinicao\tNota\tProducao\tTags\n"
    "#tags column:8\n"
)
LACUNA = '<span class="lacuna">_____</span>'
_MARCADO = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)


@dataclass(frozen=True)
class ResultadoExportacao:
    link: str
    quantidade: int
    ignoradas: int  # entradas sem nenhuma frase utilizável para o cartão


def _tem_marca(frase: str | None) -> bool:
    return frase is not None and _MARCADO.search(frase) is not None


def escolher_frase(entrada: Entry, frases: Sequence[Sentence]) -> str | None:
    """Frase do cartão (seção 7.2), com o alvo entre [[ ]]: a melhor frase do usuário (`correta`,
    senão a `versao_natural` mais recente); sem frase do usuário, o primeiro exemplo do bot."""
    do_usuario = sorted((f for f in frases if f.autor == "usuario"), key=lambda f: f.criado_em)

    corretas = [f for f in do_usuario if f.veredito == "correta"]
    if corretas:
        melhor = corretas[-1]
        marcada = (
            melhor.texto if _tem_marca(melhor.texto) else marcar_alvo(melhor.texto, entrada.palavra)
        )
        if _tem_marca(marcada):
            return marcada
        if _tem_marca(melhor.versao_natural):
            return melhor.versao_natural

    for frase in reversed(do_usuario):
        if _tem_marca(frase.versao_natural):
            return frase.versao_natural

    for frase in sorted((f for f in frases if f.autor == "bot"), key=lambda f: f.criado_em):
        if _tem_marca(frase.texto):
            return frase.texto
    return None


def _campo(texto: str) -> str:
    """Texto seguro para um campo: HTML escapado, tab vira espaço e quebra de linha vira <br>."""
    seguro = html.escape(texto, quote=False).replace("\t", " ")
    return seguro.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def _frase_em_html(frase: str, formatar_alvo: Callable[[str], str]) -> str:
    partes = _MARCADO.split(frase)  # texto, alvo, texto, alvo, ...
    return "".join(formatar_alvo(_campo(p)) if i % 2 else _campo(p) for i, p in enumerate(partes))


def linha_do_cartao(entrada: Entry, frase: str) -> str:
    campos = [
        _campo(entrada.palavra),
        _frase_em_html(frase, lambda alvo: f"<b>{alvo}</b>"),
        _frase_em_html(frase, lambda _: LACUNA),
        _campo(f"({entrada.classe}) {entrada.sentido.traducao}"),
        _campo(entrada.sentido.definicao),
        _campo(entrada.nota),
        "y",
        " ".join(["whatsapp", *entrada.tags]),
    ]
    return "\t".join(campos) + "\n"


def gerar_arquivo(cartoes: Sequence[tuple[Entry, str]]) -> str:
    return CABECALHO + "".join(linha_do_cartao(entrada, frase) for entrada, frase in cartoes)


class ExportadorAnki:
    """Implementa o `Exportador` dos comandos: monta o arquivo, guarda e devolve o link."""

    def __init__(
        self,
        repo: Repository,
        armazenamento: Armazenamento,
        agora: Callable[[], datetime] = agora_utc,
    ) -> None:
        self._repo = repo
        self._armazenamento = armazenamento
        self._agora = agora

    def exportar(self, *, tudo: bool) -> ResultadoExportacao | None:
        candidatas = [e for e in self._repo.listar_entradas() if tudo or not e.exportado]
        cartoes: list[tuple[Entry, str]] = []
        ignoradas = 0
        for entrada in candidatas:
            frase = escolher_frase(entrada, self._repo.listar_frases(entrada.slug))
            if frase is None:
                ignoradas += 1
            else:
                cartoes.append((entrada, frase))
        if not cartoes:
            return None

        agora = self._agora()
        nome = f"exports/anki_{agora:%Y-%m-%d_%H%M}.txt"
        link = self._armazenamento.enviar(nome, gerar_arquivo(cartoes).encode("utf-8"))

        # Só depois de o arquivo estar guardado: uma falha no upload não marca nada como exportado.
        for entrada, _ in cartoes:
            self._repo.salvar_entrada(
                entrada.model_copy(update={"exportado": True, "atualizado_em": agora})
            )
        return ResultadoExportacao(link=link, quantidade=len(cartoes), ignoradas=ignoradas)
