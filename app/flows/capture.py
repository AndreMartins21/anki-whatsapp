"""Captura: o aluno manda uma palavra, o bot explica e já mostra o card com o menu único (M9).

Desde o M9 a IA sempre escolhe um sentido (`sentido_do_contexto` nunca fica `null`), então não há
mais uma pergunta separada de "qual sentido" — o card já sai pronto numa mensagem só.
"""

from __future__ import annotations

from app import messages
from app.domain.models import (
    Entry,
    Estado,
    Explanation,
    Profile,
    Sense,
    Sentence,
    SentidoSalvo,
    Sessao,
    slugify,
)
from app.flows.base import Deps, bloq
from app.repo.base import EntradaJaExiste, resolver_slug


async def explicar(
    d: Deps,
    perfil: Profile,
    texto: str,
    entrada_existente: Entry | None = None,
) -> Sessao:
    """Explica `texto`. Com `entrada_existente` (expansões, /praticar), atualiza aquela entrada
    em vez de criar outra."""
    palavras_do_aluno = [e.palavra for e in await bloq(d.repo.listar_entradas)]
    async with d.conversa.digitando():
        explicacao = await bloq(d.tutor.explain, texto, perfil.nivel, palavras_do_aluno)

    if not explicacao.ok:
        await d.conversa.enviar(messages.entrada_invalida(explicacao.motivo_erro))
        return d.sessao_vazia()

    sentido_id = explicacao.sentido_do_contexto or explicacao.sentidos[0].id
    sentido = next(s for s in explicacao.sentidos if s.id == sentido_id)
    return await _comecar_pratica(d, explicacao, sentido, entrada_existente)


async def _comecar_pratica(
    d: Deps,
    explicacao: Explanation,
    sentido: Sense,
    existente: Entry | None,
) -> Sessao:
    entrada, criada_agora = await bloq(gravar_entrada, d, explicacao, sentido, existente)
    if existente is None and not criada_agora:
        return await _avisar_que_ja_existe(d, entrada, sentido)
    await bloq(
        d.repo.adicionar_frase,
        entrada.slug,
        Sentence(texto=sentido.exemplo, autor="bot", criado_em=d.agora()),
    )
    await d.conversa.enviar(
        messages.explicacao(
            entrada.palavra,
            entrada.classe,
            entrada.cefr_estimado,
            sentido,
            entrada.nota,
            sentido.exemplo,
            grupo=d.grupo_prefixo,
        )
    )
    return d.sessao_vazia().model_copy(
        update={
            "estado": Estado.AWAIT_ACTION,
            "entry_id": entrada.slug,
            "sentido_id": sentido.id,
            "entrada_criada_agora": criada_agora,
        }
    )


async def _avisar_que_ja_existe(d: Deps, entrada: Entry, sentido: Sense) -> Sessao:
    """A palavra já estava na lista: mostra o que o aluno tem (o sentido e o exemplo salvos, não os
    da explicação nova) e segue na mesma palavra, para praticar, sem regravar nada."""
    frases = await bloq(d.repo.listar_frases, entrada.slug)
    exemplo = next((f.texto for f in frases if f.autor == "bot"), sentido.exemplo)
    await d.conversa.enviar(
        messages.ja_existe(
            entrada.palavra,
            entrada.classe,
            entrada.cefr_estimado,
            entrada.sentido,
            exemplo,
            grupo=d.grupo_prefixo,
        )
    )
    return d.sessao_vazia().model_copy(
        update={
            "estado": Estado.AWAIT_ACTION,
            "entry_id": entrada.slug,
            "sentido_id": sentido.id,
        }
    )


def _entradas_da_palavra(entradas: list[Entry], palavra: str) -> list[Entry]:
    """Os sentidos salvos da palavra (`stall`, `stall--s2`...), o de slug-base primeiro."""
    base = slugify(palavra)
    dela = [e for e in entradas if e.slug == base or e.slug.startswith(f"{base}--s")]
    return sorted(dela, key=lambda e: e.slug != base)


def gravar_entrada(
    d: Deps, explicacao: Explanation, sentido: Sense, existente: Entry | None
) -> tuple[Entry, bool]:
    """A entrada gravada e se foi criada agora (`False`: já existia, ou é a atualização de uma)."""
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
        return atualizada, False

    if explicacao.frase_contexto is None:
        # Palavra sozinha, sem frase: não há um sentido escolhido pelo aluno, só o "mais comum" que
        # a IA sorteia a cada chamada. Quem já tem a palavra tem a palavra, qualquer que seja o
        # sentido salvo; só uma frase de contexto justifica abrir outro sentido.
        da_palavra = _entradas_da_palavra(d.repo.listar_entradas(), explicacao.palavra)
        if da_palavra:
            return da_palavra[0], False

    slug = resolver_slug(d.repo, explicacao.palavra, escolhido.traducao)
    ja_salva = d.repo.obter_entrada(slug)
    if ja_salva is not None:  # o aluno voltou a uma palavra que já tem: mantém as frases dela
        return ja_salva, False

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
        return d.repo.obter_entrada(slug) or entrada, False
    return entrada, True
