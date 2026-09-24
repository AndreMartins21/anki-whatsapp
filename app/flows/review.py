"""Revisão espaçada (M10, seção 5.7, ADR-0011): monta a fila de palavras vencidas, faz um turno
por vez (pergunta → resposta → feedback + próxima) e fecha com o resumo. `montar_fila` é pura
(testável sem repo); `iniciar`/`responder`/`encerrar` fazem I/O, como os demais fluxos.

Em grupo (M17, ADR-0020) cada card **marca um aluno**, escolhido por rodízio (`domain/rodizio.py`):
só a resposta da pessoa marcada vale a nota; a de outra pessoa recebe feedback sem mudar o card; e
se a marcada não responde no prazo, o card passa ao próximo aluno, uma vez, e depois a rodada fecha.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from app import messages
from app.channel.parser import numero_esta_na_lista
from app.domain.models import Entry, Estado, Membro, Profile, Resposta, Sentence, Sessao
from app.domain.rodizio import Candidato, escolher
from app.domain.srs import reagendar, vencida
from app.flows.base import Deps, bloq

logger = logging.getLogger(__name__)

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


def limite(d: Deps) -> int:
    """Palavras por rodada: 20 no privado, `LIMITE_POR_SESSAO_GRUPO` (5) no grupo."""
    return d.grupo_cfg.limite if d.em_grupo else LIMITE_POR_SESSAO


# --- quem é marcado (grupo) -------------------------------------------------------------------


def _eh_o_bot(d: Deps, numero: str) -> bool:
    bot = d.grupo_cfg.numero_do_bot
    return bot is not None and numero_esta_na_lista(numero, [bot])


async def _alunos_elegiveis(d: Deps, *, atualizar: bool) -> list[tuple[str, Membro]]:
    """Os alunos que podem ser marcados: quem está no grupo (o endpoint do WAHA, atualizado no
    início de cada rodada), sem o bot e sem professores. Sem a lista de participantes (o WAHA
    falhou), vale o cadastro de membros. Quem está no grupo e nunca escreveu com prefixo entra no
    cadastro como aluno."""
    cfg = d.grupo_cfg
    presentes: list[str] | None = None
    if atualizar and cfg.participantes is not None:
        try:
            numeros = await cfg.participantes(d.chat_id)
        except Exception:
            logger.warning("não consegui listar os participantes do grupo; uso o cadastro")
        else:
            # Uma lista vazia não é confiável (o próprio bot deveria estar nela): usa o cadastro.
            if numeros:
                presentes = [n for n in numeros if not _eh_o_bot(d, n)]
                await bloq(_cadastrar_novos, d, presentes)
    membros = await bloq(d.repo.listar_membros)
    return [
        (numero, membro)
        for numero, membro in membros
        if membro.papel == "aluno"
        and not _eh_o_bot(d, numero)
        and (presentes is None or numero_esta_na_lista(numero, presentes))
    ]


def _cadastrar_novos(d: Deps, presentes: Sequence[str]) -> None:
    conhecidos = [numero for numero, _ in d.repo.listar_membros()]
    for numero in presentes:
        if not numero_esta_na_lista(numero, conhecidos):
            d.repo.salvar_membro(numero, Membro(entrou_em=d.agora()))


async def _marcar(
    d: Deps, alunos: Sequence[tuple[str, Membro]], *, excluir: str | None
) -> str | None:
    """Escolhe quem marcar pelo rodízio e anota a marcação. `None` se não há aluno."""
    candidatos = [Candidato(numero, membro.marcado_em) for numero, membro in alunos]
    escolhido = escolher(candidatos, excluir=excluir, sortear=d.grupo_cfg.sortear)
    if escolhido is None:
        return None
    membro = next(m for n, m in alunos if n == escolhido)
    await bloq(d.repo.salvar_membro, escolhido, membro.model_copy(update={"marcado_em": d.agora()}))
    return escolhido


# --- a rodada ---------------------------------------------------------------------------------


async def iniciar(d: Deps, *, avisar: bool = False) -> Sessao:
    """Começa a rodada. `avisar`: num grupo sem aluno para marcar, diz por que não começou (o
    `!review`); o lembrete agendado (`avisar=False`) fica em silêncio."""
    entradas = await bloq(d.repo.listar_entradas)
    fila = montar_fila(entradas, d.agora(), limite=limite(d))
    if not fila:
        return d.sessao_vazia()
    alunos: list[tuple[str, Membro]] | None = None
    if d.em_grupo:
        alunos = await _alunos_elegiveis(d, atualizar=True)
        if not alunos:
            if avisar:
                await d.conversa.enviar(messages.grupo_sem_aluno(d.p))
            return d.sessao_vazia()
    d.conversa.nova_iniciativa()  # o bot está iniciando, não respondendo — reseta o limite de 3
    total = len(fila)
    return await _mostrar_proxima(
        d, messages.hora_da_pratica(total), fila, [], [], total, alunos=alunos
    )


def _mesma_pessoa(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and numero_esta_na_lista(a, [b])


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
            anterior=sessao.marcado_id,
        )

    async with d.conversa.digitando():
        revisao = await bloq(d.tutor.review, entrada.palavra, entrada.sentido, texto, perfil.nivel)

    agora = d.agora()
    # Em grupo só a pessoa marcada vale a nota (sem marcada, como no privado, quem responde vale).
    conta = (
        not d.em_grupo or sessao.marcado_id is None or _mesma_pessoa(d.autor_id, sessao.marcado_id)
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
    if d.em_grupo and d.autor_id:
        await bloq(
            d.repo.registrar_resposta,
            Resposta(
                entry=entrada.slug,
                autor_id=d.autor_id,
                marcado=conta and sessao.marcado_id is not None,
                qualidade=revisao.qualidade,
                criado_em=agora,
            ),
        )
    if not conta:
        # Feedback, mas o cartão, a nota e o card atual não mudam.
        await d.conversa.enviar(messages.feedback_sem_nota(revisao))
        return sessao

    agendamento = reagendar(entrada, revisao.qualidade, agora)
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

    feitas = [*sessao.revisao_feitas, entrada.palavra]
    fila = list(sessao.revisao_fila)
    lapsos = list(sessao.revisao_lapsos)
    if revisao.qualidade == "de_novo":
        fila = [*fila, entrada.slug]  # volta ao fim da fila DESTA sessão, como no Anki
        lapsos = [*lapsos, entrada.palavra]

    feedback = messages.feedback_de_revisao(revisao)
    return await _mostrar_proxima(
        d, feedback, fila, feitas, lapsos, sessao.revisao_total, anterior=sessao.marcado_id
    )


async def encerrar(d: Deps, sessao: Sessao) -> Sessao:
    await d.conversa.enviar(
        messages.revisao_encerrada(sessao.revisao_feitas, sessao.revisao_lapsos, p=d.p)
    )
    return d.sessao_vazia()


async def sem_resposta(d: Deps, sessao: Sessao) -> Sessao:
    """A pessoa marcada não respondeu no prazo (M17, chamado pelo agendador): na primeira vez o
    card passa ao próximo aluno do rodízio; na segunda a rodada fecha com o resumo."""
    entrada = (
        await bloq(d.repo.obter_entrada, sessao.revisao_atual) if sessao.revisao_atual else None
    )
    if sessao.marcacao_tentativas < 1 and entrada is not None:
        alunos = await _alunos_elegiveis(d, atualizar=False)
        novo = await _marcar(d, alunos, excluir=sessao.marcado_id)
        if novo is not None:
            indice = min(len(sessao.revisao_feitas) + 1, sessao.revisao_total)
            await d.conversa.enviar(
                messages.repasse(indice, sessao.revisao_total, entrada.palavra, novo, d.p),
                mentions=[novo],
            )
            return sessao.model_copy(
                update={
                    "marcado_id": novo,
                    "marcacao_expira_em": d.agora() + d.grupo_cfg.timeout,
                    "marcacao_tentativas": sessao.marcacao_tentativas + 1,
                }
            )
    await d.conversa.enviar(
        messages.revisao_sem_resposta(sessao.revisao_feitas, sessao.revisao_lapsos, p=d.p)
    )
    return d.sessao_vazia()


async def _mostrar_proxima(
    d: Deps,
    feedback: str,
    fila: list[str],
    feitas: list[str],
    lapsos: list[str],
    total: int,
    *,
    alunos: list[tuple[str, Membro]] | None = None,
    anterior: str | None = None,
) -> Sessao:
    """Mostra a próxima palavra da fila (pulando entradas apagadas no meio da revisão) numa
    mensagem só com o feedback, ou encerra com o resumo se a fila acabou. Em grupo, o card marca
    o próximo aluno do rodízio (nunca o mesmo `anterior`, se houver outro)."""
    restante = list(fila)
    while restante:
        slug = restante.pop(0)
        entrada = await bloq(d.repo.obter_entrada, slug)
        if entrada is None:
            continue
        indice = min(len(feitas) + 1, total)
        marcado: str | None = None
        if d.em_grupo:
            if alunos is None:
                alunos = await _alunos_elegiveis(d, atualizar=False)
            marcado = await _marcar(d, alunos, excluir=anterior)
        card = messages.card_de_revisao(
            indice, total, entrada.palavra, grupo=d.grupo_prefixo, marcado=marcado
        )
        await d.conversa.enviar(
            f"{feedback}\n\n{card}" if feedback else card, mentions=[marcado] if marcado else None
        )
        return Sessao(
            estado=Estado.REVIEWING,
            revisao_fila=restante,
            revisao_atual=slug,
            revisao_feitas=feitas,
            revisao_lapsos=lapsos,
            revisao_total=total,
            marcado_id=marcado,
            marcacao_expira_em=(d.agora() + d.grupo_cfg.timeout) if marcado else None,
            atualizado_em=d.agora(),
        )

    resumo = messages.revisao_encerrada(feitas, lapsos, p=d.p)
    await d.conversa.enviar(f"{feedback}\n\n{resumo}" if feedback else resumo)
    return d.sessao_vazia()
