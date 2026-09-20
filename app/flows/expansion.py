"""Expansões: depois de salvar, sugere expressões relacionadas; as escolhidas viram entradas "nova"."""

from __future__ import annotations

import logging

from app import messages
from app.domain.models import (
    Entry,
    Estado,
    Expansion,
    Profile,
    SentidoSalvo,
    Sessao,
    Tag,
)
from app.flows import capture
from app.flows.base import Deps, bloq
from app.repo.base import resolver_slug
from app.services.llm import LLMError

logger = logging.getLogger(__name__)

_CLASSE_POR_TIPO = {
    "colocacao": "colocação",
    "familia": "família de palavras",
    "phrasal_verb": "phrasal verb",
    "sinonimo": "sinônimo",
    "expressao": "expressão",
}
_TAGS_POR_TIPO: dict[str, list[Tag]] = {
    "phrasal_verb": ["phrasal_verb"],
    "expressao": ["expressao"],
}


async def oferecer(d: Deps, sessao: Sessao, perfil: Profile, entrada: Entry) -> Sessao:
    existentes = [e.palavra for e in await bloq(d.repo.listar_entradas)]
    try:
        async with d.conversa.digitando():
            sugestoes = await bloq(
                d.tutor.expansions, entrada.palavra, entrada.sentido, perfil.nivel, existentes
            )
    except LLMError:
        # A palavra já está salva; só não há sugestões desta vez.
        logger.warning("sem expansões para %s", entrada.slug, exc_info=True)
        await d.conversa.enviar(messages.salvo(entrada.palavra))
        return d.sessao_vazia()

    await d.conversa.enviar(messages.salvo_com_expansoes(entrada.palavra, sugestoes))
    return sessao.model_copy(
        update={"estado": Estado.OFFER_EXPANSION, "expansoes_sugeridas": sugestoes}
    )


async def criar(d: Deps, sessao: Sessao, numeros: tuple[int, ...]) -> Sessao:
    escolhidas = [sessao.expansoes_sugeridas[n - 1] for n in numeros]
    criadas: list[str] = []
    ja_existiam = 0
    for expansao in escolhidas:
        slug = await bloq(_criar_entrada_da_expansao, d, expansao, sessao.entry_id)
        if slug is None:
            ja_existiam += 1
        else:
            criadas.append(slug)

    await d.conversa.enviar(messages.expansoes_criadas(len(criadas), ja_existiam))
    if not criadas:
        return d.sessao_vazia()
    return d.sessao_vazia().model_copy(
        update={"estado": Estado.AWAIT_EXPANSION_PRACTICE, "expansoes_criadas": criadas}
    )


async def praticar_agora(d: Deps, sessao: Sessao, perfil: Profile) -> Sessao:
    if not sessao.expansoes_criadas:
        return d.sessao_vazia()
    entrada = await bloq(d.repo.obter_entrada, sessao.expansoes_criadas[0])
    if entrada is None:
        return d.sessao_vazia()
    return await capture.explicar(d, perfil, entrada.palavra, entrada_existente=entrada)


def _criar_entrada_da_expansao(d: Deps, expansao: Expansion, pai: str | None) -> str | None:
    """Cria a entrada `nova` (só com o que a sugestão traz; o resto vem ao praticar). Devolve
    o slug, ou `None` se o aluno já tinha essa expressão."""
    slug = resolver_slug(d.repo, expansao.expressao, expansao.traducao)
    if d.repo.obter_entrada(slug) is not None:
        return None
    agora = d.agora()
    d.repo.criar_entrada(
        Entry(
            slug=slug,
            palavra=expansao.expressao,
            classe=_CLASSE_POR_TIPO[expansao.tipo],
            cefr_estimado="B1",
            sentido=SentidoSalvo(traducao=expansao.traducao, definicao=""),
            tags=_TAGS_POR_TIPO.get(expansao.tipo, []),
            origem="expansao",
            pai=pai,
            criado_em=agora,
            atualizado_em=agora,
        )
    )
    return slug
