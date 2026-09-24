"""Revisão espaçada (M10, seção 5.7, ADR-0011): monta a fila de palavras vencidas, faz um turno
por vez (pergunta → resposta → feedback + próxima) e fecha com o resumo. `montar_fila` é pura
(testável sem repo); `iniciar`/`responder`/`encerrar` fazem I/O, como os demais fluxos."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app import messages
from app.domain.models import Entry, Estado, Profile, Sentence, Sessao
from app.domain.srs import reagendar, vencida
from app.flows.base import Deps, bloq

LIMITE_POR_SESSAO = 20


def montar_fila(
    entradas: Sequence[Entry], agora: datetime, limite: int = LIMITE_POR_SESSAO
) -> list[str]:
    """Vencidas primeiro (mais antiga primeiro), até `limite`. Sem vencidas suficientes, completa
    com as que vencem mais cedo. Sem nenhuma entrada, devolve a fila vazia (sem revisão)."""
    vencidas = sorted(
        (e for e in entradas if vencida(e, agora)), key=lambda e: e.proxima_revisao or e.criado_em
    )
    if len(vencidas) >= limite:
        return [e.slug for e in vencidas[:limite]]

    restantes = sorted(
        (e for e in entradas if not vencida(e, agora)),
        key=lambda e: e.proxima_revisao or e.criado_em,
    )
    completar = restantes[: limite - len(vencidas)]
    return [e.slug for e in (*vencidas, *completar)]


async def iniciar(d: Deps) -> Sessao:
    entradas = await bloq(d.repo.listar_entradas)
    fila = montar_fila(entradas, d.agora())
    if not fila:
        return d.sessao_vazia()
    d.conversa.nova_iniciativa()  # o bot está iniciando, não respondendo — reseta o limite de 3
    total = len(fila)
    return await _mostrar_proxima(d, messages.hora_da_pratica(total), fila, [], [], total)


async def responder(d: Deps, sessao: Sessao, perfil: Profile, texto: str) -> Sessao:
    entrada = (
        await bloq(d.repo.obter_entrada, sessao.revisao_atual) if sessao.revisao_atual else None
    )
    if entrada is None:  # apagada no meio da revisão (ex.: /apagar): pula sem feedback
        return await _mostrar_proxima(
            d,
            "",
            sessao.revisao_fila,
            sessao.revisao_feitas,
            sessao.revisao_lapsos,
            sessao.revisao_total,
        )

    async with d.conversa.digitando():
        revisao = await bloq(d.tutor.review, entrada.palavra, entrada.sentido, texto, perfil.nivel)

    agendamento = reagendar(entrada, revisao.qualidade, d.agora())
    agora = d.agora()
    await bloq(
        d.repo.salvar_entrada,
        entrada.model_copy(
            update={
                "repeticoes": agendamento.repeticoes,
                "intervalo_dias": agendamento.intervalo_dias,
                "facilidade": agendamento.facilidade,
                "proxima_revisao": agendamento.proxima_revisao,
                "lapsos": agendamento.lapsos,
                "revisada_em": agora,
                "atualizado_em": agora,
            }
        ),
    )
    if revisao.tipo == "frase":
        await bloq(
            d.repo.adicionar_frase,
            entrada.slug,
            Sentence(
                texto=texto,
                autor="usuario",
                autor_id=d.autor_id,
                versao_natural=revisao.correcao or None,
                criado_em=agora,
            ),
        )

    feitas = [*sessao.revisao_feitas, entrada.palavra]
    fila = list(sessao.revisao_fila)
    lapsos = list(sessao.revisao_lapsos)
    if revisao.qualidade == "de_novo":
        fila = [*fila, entrada.slug]  # volta ao fim da fila DESTA sessão, como no Anki
        lapsos = [*lapsos, entrada.palavra]

    feedback = messages.feedback_de_revisao(revisao)
    return await _mostrar_proxima(d, feedback, fila, feitas, lapsos, sessao.revisao_total)


async def encerrar(d: Deps, sessao: Sessao) -> Sessao:
    await d.conversa.enviar(
        messages.revisao_encerrada(sessao.revisao_feitas, sessao.revisao_lapsos)
    )
    return d.sessao_vazia()


async def _mostrar_proxima(
    d: Deps, feedback: str, fila: list[str], feitas: list[str], lapsos: list[str], total: int
) -> Sessao:
    """Mostra a próxima palavra da fila (pulando entradas apagadas no meio da revisão) numa
    mensagem só com o feedback, ou encerra com o resumo se a fila acabou."""
    restante = list(fila)
    while restante:
        slug = restante.pop(0)
        entrada = await bloq(d.repo.obter_entrada, slug)
        if entrada is None:
            continue
        indice = min(len(feitas) + 1, total)
        card = messages.card_de_revisao(indice, total, entrada.palavra, grupo=d.grupo_prefixo)
        await d.conversa.enviar(f"{feedback}\n\n{card}" if feedback else card)
        return Sessao(
            estado=Estado.REVIEWING,
            revisao_fila=restante,
            revisao_atual=slug,
            revisao_feitas=feitas,
            revisao_lapsos=lapsos,
            revisao_total=total,
            atualizado_em=d.agora(),
        )

    resumo = messages.revisao_encerrada(feitas, lapsos)
    await d.conversa.enviar(f"{feedback}\n\n{resumo}" if feedback else resumo)
    return d.sessao_vazia()
