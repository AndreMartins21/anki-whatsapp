"""Horários dos lembretes de revisão espaçada (M10, seção 5.7): distribuição igual numa janela
do dia, e o parser do argumento de `/lembretes`. Função pura, sem fuso: quem converte para o fuso
do aluno é o chamador (`app/services/lembretes.py`)."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.models import Profile

MIN_LEMBRETES = 1
MAX_LEMBRETES = 8
JANELA_PADRAO_INICIO = 9
JANELA_PADRAO_FIM = 21

# Tamanho da fila de revisão (M24, seção 5.7): dinâmico por padrão (`MIN(palavras do aluno, isto)`)
# até a pessoa fixar um valor com `/reviewsize` ou o último parâmetro de `/reminders`.
TAMANHO_REVISAO_PADRAO = 7
MIN_TAMANHO_REVISAO = 1
MAX_TAMANHO_REVISAO = 20

_SO_QUANTIDADE = re.compile(r"^(\d+)$")
_QUANTIDADE_E_TAMANHO = re.compile(r"^(\d+)\s+(\d+)$")
_QUANTIDADE_E_JANELA = re.compile(r"^(\d+)\s+(\d{1,2})h-(\d{1,2})h$")
_QUANTIDADE_JANELA_E_TAMANHO = re.compile(r"^(\d+)\s+(\d{1,2})h-(\d{1,2})h\s+(\d+)$")


def horarios_do_dia(quantidade: int, inicio: int, fim: int) -> list[time]:
    """`quantidade` horários entre `inicio` e `fim` (horas cheias, 0-23), igualmente espaçados.
    Com 1 horário, cai no início da janela."""
    if quantidade == 1:
        return [time(inicio)]
    passo = (fim - inicio) / (quantidade - 1)
    horarios = []
    for i in range(quantidade):
        minutos_totais = round((inicio * 60) + i * passo * 60)
        horarios.append(time(minutos_totais // 60, minutos_totais % 60))
    return horarios


def proximo_horario(agora_local: datetime, quantidade: int, inicio: int, fim: int) -> datetime:
    """O próximo horário da janela a partir de `agora_local` — hoje, se ainda não passou, senão
    o primeiro horário de amanhã."""
    horarios = horarios_do_dia(quantidade, inicio, fim)
    hoje = agora_local.date()
    for horario in horarios:
        candidato = agora_local.replace(
            hour=horario.hour, minute=horario.minute, second=0, microsecond=0
        )
        if candidato > agora_local:
            return candidato
    amanha = hoje + timedelta(days=1)
    primeiro = horarios[0]
    return agora_local.replace(
        year=amanha.year,
        month=amanha.month,
        day=amanha.day,
        hour=primeiro.hour,
        minute=primeiro.minute,
        second=0,
        microsecond=0,
    )


def proximo_a_exibir(perfil: Profile, agora: datetime, fuso: ZoneInfo) -> datetime | None:
    """Quando o próximo lembrete toca, no fuso do aluno; `None` com os lembretes desligados.
    Usa o horário já agendado em `profile/me` se ainda está no futuro; senão (recém-ligado, ou o
    agendador ainda não recalculou) calcula o próximo horário da janela a partir de `agora`."""
    if perfil.lembretes_por_dia == 0:
        return None
    if perfil.proximo_lembrete is not None and perfil.proximo_lembrete > agora:
        return perfil.proximo_lembrete.astimezone(fuso)
    return proximo_horario(
        agora.astimezone(fuso), perfil.lembretes_por_dia, perfil.janela_inicio, perfil.janela_fim
    )


def parse_lembretes(argumento: str) -> tuple[int, int, int, int | None] | None:
    """`"3"` -> `(3, 9, 21, None)` (janela padrão; `None` no tamanho = não veio no comando, quem
    chama não mexe no que já estava); `"3 9h-22h"` -> `(3, 9, 22, None)`; `"3 9h-22h 10"` ->
    `(3, 9, 22, 10)`; `"3 10"` -> `(3, 9, 21, 10)` (tamanho sem mudar a janela). `None` geral
    (não a tupla) se o formato, a quantidade (1-8), a janela (`0 <= inicio < fim <= 23`) ou o
    tamanho da fila (1-20, quando veio) forem inválidos."""
    texto = argumento.strip().lower()
    tamanho: int | None
    casamento_completo = _QUANTIDADE_JANELA_E_TAMANHO.match(texto)
    if casamento_completo:
        quantidade = int(casamento_completo[1])
        inicio = int(casamento_completo[2])
        fim = int(casamento_completo[3])
        tamanho = int(casamento_completo[4])
    else:
        casamento_com_janela = _QUANTIDADE_E_JANELA.match(texto)
        if casamento_com_janela:
            quantidade = int(casamento_com_janela[1])
            inicio = int(casamento_com_janela[2])
            fim = int(casamento_com_janela[3])
            tamanho = None
        else:
            casamento_com_tamanho = _QUANTIDADE_E_TAMANHO.match(texto)
            if casamento_com_tamanho:
                quantidade = int(casamento_com_tamanho[1])
                inicio, fim = JANELA_PADRAO_INICIO, JANELA_PADRAO_FIM
                tamanho = int(casamento_com_tamanho[2])
            else:
                casamento_simples = _SO_QUANTIDADE.match(texto)
                if not casamento_simples:
                    return None
                quantidade = int(casamento_simples[1])
                inicio, fim = JANELA_PADRAO_INICIO, JANELA_PADRAO_FIM
                tamanho = None

    if not (MIN_LEMBRETES <= quantidade <= MAX_LEMBRETES):
        return None
    if not (0 <= inicio < fim <= 23):
        return None
    if tamanho is not None and not (MIN_TAMANHO_REVISAO <= tamanho <= MAX_TAMANHO_REVISAO):
        return None
    return quantidade, inicio, fim, tamanho


def parse_tamanho_revisao(argumento: str) -> int | None:
    """`/reviewsize N`, um tamanho fixo de 1 a 20. `None` se não for um número nessa faixa (quem
    chama trata `"auto"`/`"off"` à parte, como o `/reminders off`)."""
    texto = argumento.strip().lower()
    if not texto.isdigit():
        return None
    tamanho = int(texto)
    if not (MIN_TAMANHO_REVISAO <= tamanho <= MAX_TAMANHO_REVISAO):
        return None
    return tamanho
