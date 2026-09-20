"""Captura: o aluno manda uma palavra, o bot explica e, se preciso, pergunta o sentido."""

from __future__ import annotations

from app import messages
from app.domain.models import (
    Entry,
    Estado,
    Explanation,
    Profile,
    Sense,
    SentidoSalvo,
    Sessao,
)
from app.domain.state import estado_apos_explicar
from app.flows.base import Deps, bloq
from app.repo.base import EntradaJaExiste, resolver_slug


def _sentido_definido(explicacao: Explanation) -> str | None:
    """O contexto define o sentido, ou só existe um sentido comum: não há o que perguntar."""
    if explicacao.sentido_do_contexto:
        return explicacao.sentido_do_contexto
    if len(explicacao.sentidos) == 1:
        return explicacao.sentidos[0].id
    return None


async def explicar(
    d: Deps,
    perfil: Profile,
    texto: str,
    entrada_existente: Entry | None = None,
) -> Sessao:
    """Explica `texto`. Com `entrada_existente` (expansões, /praticar), atualiza aquela entrada
    em vez de criar outra."""
    async with d.conversa.digitando():
        explicacao = await bloq(d.tutor.explain, texto, perfil.nivel)

    if not explicacao.ok:
        await d.conversa.enviar(messages.entrada_invalida(explicacao.motivo_erro))
        return d.sessao_vazia()

    sentido_id = _sentido_definido(explicacao)
    if sentido_id is None:
        await d.conversa.enviar(
            messages.escolha_de_sentido(
                explicacao.palavra, explicacao.classe, explicacao.cefr_estimado, explicacao.sentidos
            )
        )
        return d.sessao_vazia().model_copy(
            update={
                "estado": Estado.AWAIT_SENSE,
                "entry_id": entrada_existente.slug if entrada_existente else None,
                "explicacao_pendente": explicacao,
            }
        )

    sentido = next(s for s in explicacao.sentidos if s.id == sentido_id)
    return await _comecar_pratica(d, perfil, explicacao, sentido, entrada_existente)


async def escolher_sentido(d: Deps, sessao: Sessao, perfil: Profile, numero: int) -> Sessao:
    explicacao = sessao.explicacao_pendente
    if explicacao is None:  # sessão inconsistente: melhor recomeçar do que travar
        return d.sessao_vazia()
    sentido = explicacao.sentidos[numero - 1]
    existente = await bloq(d.repo.obter_entrada, sessao.entry_id) if sessao.entry_id else None
    return await _comecar_pratica(d, perfil, explicacao, sentido, existente)


async def perguntar_nova_palavra(d: Deps, sessao: Sessao, texto: str) -> Sessao:
    await d.conversa.enviar(messages.pergunta_nova_palavra(texto))
    return sessao.model_copy(update={"pendente_nova_palavra": texto})


async def _comecar_pratica(
    d: Deps,
    perfil: Profile,
    explicacao: Explanation,
    sentido: Sense,
    existente: Entry | None,
) -> Sessao:
    entrada = await bloq(_gravar_entrada, d, explicacao, sentido, existente)
    await d.conversa.enviar(
        messages.explicacao(
            entrada.palavra,
            entrada.classe,
            entrada.cefr_estimado,
            sentido,
            entrada.nota or sentido.exemplo_curto,
            perfil.modo,
        )
    )
    return d.sessao_vazia().model_copy(
        update={
            "estado": estado_apos_explicar(False, perfil.modo),
            "entry_id": entrada.slug,
            "sentido_id": sentido.id,
        }
    )


def _gravar_entrada(
    d: Deps, explicacao: Explanation, sentido: Sense, existente: Entry | None
) -> Entry:
    agora = d.agora()
    escolhido = SentidoSalvo(traducao=sentido.traducao, definicao=sentido.definicao)
    outros = [
        SentidoSalvo(traducao=s.traducao, definicao=s.definicao)
        for s in explicacao.sentidos
        if s.id != sentido.id
    ]
    if existente is not None:
        # Uma expansão é uma expressão ("mitigate risk"): a IA a explica pela forma base ("mitigate"),
        # mas o cartão continua sendo da expressão que o aluno escolheu, com a classe da sugestão.
        da_expansao = existente.origem == "expansao"
        atualizada = existente.model_copy(
            update={
                "palavra": existente.palavra if da_expansao else explicacao.palavra,
                "classe": existente.classe if da_expansao else explicacao.classe,
                "cefr_estimado": explicacao.cefr_estimado,
                "sentido": escolhido,
                "outros_sentidos": outros,
                "nota": explicacao.nota,
                "tags": explicacao.tags,
                "atualizado_em": agora,
            }
        )
        d.repo.salvar_entrada(atualizada)
        return atualizada

    slug = resolver_slug(d.repo, explicacao.palavra, escolhido.traducao)
    ja_salva = d.repo.obter_entrada(slug)
    if ja_salva is not None:  # o aluno voltou a uma palavra que já tem: mantém as frases dela
        return ja_salva

    entrada = Entry(
        slug=slug,
        palavra=explicacao.palavra,
        classe=explicacao.classe,
        cefr_estimado=explicacao.cefr_estimado,
        sentido=escolhido,
        outros_sentidos=outros,
        nota=explicacao.nota,
        tags=explicacao.tags,
        origem_texto=explicacao.frase_contexto,
        criado_em=agora,
        atualizado_em=agora,
    )
    try:
        d.repo.criar_entrada(entrada)
    except EntradaJaExiste:
        return d.repo.obter_entrada(slug) or entrada
    return entrada
