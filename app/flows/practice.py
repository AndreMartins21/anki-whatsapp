"""Prática: pedir frase, exemplos, avaliação e conclusão (que oferece as expansões)."""

from __future__ import annotations

from datetime import timedelta

from app import messages
from app.domain.models import Entry, Profile, Sentence, Sessao
from app.flows import expansion
from app.flows.base import Deps, bloq

NUMERO_DE_EXEMPLOS = 3


async def _entrada_atual(d: Deps, sessao: Sessao) -> Entry:
    entrada = await bloq(d.repo.obter_entrada, sessao.entry_id) if sessao.entry_id else None
    if entrada is None:
        raise RuntimeError("sessão sem entrada em andamento")
    return entrada


async def pedir_frase(d: Deps, sessao: Sessao, perfil: Profile) -> Sessao:
    entrada = await _entrada_atual(d, sessao)
    await d.conversa.enviar(messages.pedido_de_frase(entrada.palavra, perfil.modo))
    return sessao


async def gerar_exemplos(d: Deps, sessao: Sessao, perfil: Profile) -> Sessao:
    entrada = await _entrada_atual(d, sessao)
    async with d.conversa.digitando():
        frases = await bloq(
            d.tutor.examples, entrada.palavra, entrada.sentido, perfil.nivel, NUMERO_DE_EXEMPLOS
        )

    agora = d.agora()
    for posicao, frase in enumerate(frases):
        # microssegundos distintos: as frases voltam em ordem na listagem
        criada_em = agora + timedelta(microseconds=posicao)
        await bloq(
            d.repo.adicionar_frase,
            entrada.slug,
            Sentence(texto=frase, autor="bot", criado_em=criada_em),
        )
    await d.conversa.enviar(messages.exemplos(entrada.palavra, entrada.sentido.traducao, frases))
    return sessao


async def avaliar(d: Deps, sessao: Sessao, perfil: Profile, frase: str) -> Sessao:
    entrada = await _entrada_atual(d, sessao)
    async with d.conversa.digitando():
        avaliacao = await bloq(
            d.tutor.evaluate, entrada.palavra, entrada.sentido, frase, perfil.nivel
        )

    agora = d.agora()
    await bloq(
        d.repo.adicionar_frase,
        entrada.slug,
        Sentence(
            texto=frase,
            autor="usuario",
            veredito=avaliacao.veredito,
            correcoes=avaliacao.correcoes,
            versao_natural=avaliacao.versao_natural,
            explicacao=avaliacao.explicacao,
            criado_em=agora,
        ),
    )
    # Uma entrada vira "praticada" quando tem ao menos uma frase do usuário avaliada (seção 7.2).
    await bloq(
        d.repo.salvar_entrada,
        entrada.model_copy(update={"status": "praticada", "atualizado_em": agora}),
    )
    await d.conversa.enviar(messages.avaliacao(avaliacao, entrada.sentido.traducao))
    return sessao


async def concluir(d: Deps, sessao: Sessao, perfil: Profile, *, oferecer_expansoes: bool) -> Sessao:
    """Fecha a palavra. Tudo já está no banco (a entrada e as frases são gravadas conforme o
    aluno avança); aqui só se confere o status e, se pedido, oferecem-se as expansões."""
    entrada = await _entrada_atual(d, sessao)
    frases = await bloq(d.repo.listar_frases, entrada.slug)
    praticada = any(f.autor == "usuario" and f.veredito is not None for f in frases)
    status = "praticada" if praticada else "nova"
    if status != entrada.status:
        await bloq(
            d.repo.salvar_entrada,
            entrada.model_copy(update={"status": status, "atualizado_em": d.agora()}),
        )
    if not oferecer_expansoes:
        return d.sessao_vazia()
    return await expansion.oferecer(d, sessao, perfil, entrada)
