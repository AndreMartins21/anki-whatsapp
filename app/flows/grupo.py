"""O grupo (M16, ADR-0019): o bot só reage a mensagens com o prefixo (`!`) e a um conjunto FECHADO
de comandos; o resto é conversa entre pessoas, que ele não lê nem grava.

Camada por cima da máquina de estados, sem IA fora de atividade:

- **Comandos** (`!add`, `!list`, `!practice`, `!review`, `!reminder`, `!group`, `!help`), mais
  `!teacher`/`!student` (escondidos do `!help`).
- **Dentro de uma atividade** (`AWAIT_ACTION`, `REVIEWING`), `!1`, `!2`, `!3` e `!texto` são as
  respostas, entregues à mesma máquina de estados do privado (`conversar`).
- **Fora de atividade**, qualquer outra coisa recebe a ajuda do grupo, sem chamar a IA.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

from app import messages
from app.channel.parser import numero_esta_na_lista
from app.domain.choices import normalizar
from app.domain.lembretes import proximo_a_exibir
from app.domain.models import Estado, Membro, Papel, Profile, Sessao
from app.domain.srs import vencida
from app.flows import capture, commands, practice
from app.flows.base import Autor, Deps, bloq

logger = logging.getLogger(__name__)

# Fecha o conjunto: nada além disto é comando no grupo.
COMANDOS = {"add", "list", "practice", "review", "reminder", "reminders", "group", "help"}
_PAPEIS = {"teacher": "professor", "student": "aluno"}

Conversar = Callable[[Deps, Sessao, Profile, str], Awaitable[Sessao]]


def sem_prefixo(texto: str, prefixo: str) -> str | None:
    """O texto sem o prefixo, ou `None` se a mensagem é conversa: não começa com ele, ou não tem
    letra/número logo depois (`!!!`, `! `, `!` sozinho não chamam o bot)."""
    limpo = texto.strip()
    if not limpo.startswith(prefixo):
        return None
    resto = limpo[len(prefixo) :]
    return resto.strip() if resto[:1].isalnum() else None


def _comando(texto: str) -> tuple[str, str]:
    partes = texto.split(maxsplit=1)
    return (normalizar(partes[0]) if partes else ""), (partes[1].strip() if len(partes) > 1 else "")


async def tratar(
    d: Deps,
    sessao: Sessao,
    perfil: Profile,
    texto: str,
    *,
    autor: Autor,
    conversar: Conversar,
    eh_dono: Callable[[str], bool],
) -> Sessao:
    """`texto` já vem sem o prefixo. Devolve a nova sessão."""
    await bloq(registrar_membro, d, autor)
    estado = Estado(sessao.estado)
    comando, argumento = _comando(texto)

    if comando in _PAPEIS:
        return await _papel(d, sessao, autor, comando, argumento, eh_dono)

    if estado == Estado.REVIEWING:
        # Na revisão o texto é a resposta; só sair e pedir ajuda escapam disso.
        if comando == "stop":
            return await conversar(d, sessao, perfil, "0")
        if comando == "help":
            await d.conversa.enviar(messages.ajuda_do_grupo(d.p))
            return sessao
        return await conversar(d, sessao, perfil, texto)

    if comando in COMANDOS:
        return await _executar(d, sessao, perfil, comando, argumento)

    if estado == Estado.AWAIT_ACTION:
        return await conversar(d, sessao, perfil, texto)

    await d.conversa.enviar(messages.ajuda_do_grupo(d.p))  # sem atividade: nada de IA
    return sessao


async def _executar(
    d: Deps, sessao: Sessao, perfil: Profile, comando: str, argumento: str
) -> Sessao:
    if comando == "help":
        await d.conversa.enviar(messages.ajuda_do_grupo(d.p))
    elif comando == "list":
        await commands.listar(d, argumento)
    elif comando == "practice":
        return await commands.praticar(d, sessao, perfil, argumento)
    elif comando == "review":
        return await commands.revisar(d, sessao)
    elif comando in {"reminder", "reminders"}:
        await commands.lembretes(d, perfil, argumento)
    elif comando == "group":
        await _perfil_do_grupo(d, perfil)
    elif comando == "add":
        return await _adicionar(d, sessao, perfil, argumento)
    return sessao


async def _adicionar(d: Deps, sessao: Sessao, perfil: Profile, palavra: str) -> Sessao:
    """`!add` é a ÚNICA forma de trazer uma palavra nova para o grupo (aceita contexto:
    `!add stall | the talks stalled`). Com outra palavra aberta, salva a anterior antes, como o
    privado faz com uma palavra nova."""
    if not palavra:
        await d.conversa.enviar(messages.grupo_add_uso(d.p))
        return sessao
    if Estado(sessao.estado) == Estado.AWAIT_ACTION and sessao.entry_id:
        await practice.concluir(d, sessao, perfil)
    return await capture.explicar(d, perfil, palavra)


# --- membros e papéis -------------------------------------------------------------------------


def registrar_membro(d: Deps, autor: Autor) -> Membro:
    """Quem manda a primeira mensagem com prefixo entra como aluno; o nome do WhatsApp, quando
    vem, atualiza o cadastro (nunca o telefone)."""
    membro = d.repo.obter_membro(autor.numero)
    if membro is None:
        membro = Membro(nome=autor.nome, entrou_em=d.agora())
        d.repo.salvar_membro(autor.numero, membro)
    elif autor.nome and membro.nome != autor.nome:
        membro = membro.model_copy(update={"nome": autor.nome})
        d.repo.salvar_membro(autor.numero, membro)
    return membro


def _alvos(autor: Autor, argumento: str) -> list[str]:
    """Os números de `!teacher`/`!student`: os mencionados (se o payload os trouxer) ou o número
    escrito no texto (`!teacher 5531999998888`, com ou sem `@`)."""
    if autor.mencionados:
        return list(autor.mencionados)
    digitos = re.sub(r"\D", "", argumento)
    return [digitos] if len(digitos) >= 10 else []


def _achar_membro(d: Deps, numero: str) -> tuple[str, Membro | None]:
    existentes = d.repo.listar_membros()
    for chave, membro in existentes:
        if numero_esta_na_lista(numero, [chave]):  # tolera o nono dígito
            return chave, membro
    return numero, None


def _definir_papel(d: Deps, numero: str, papel: Papel) -> Membro:
    chave, membro = _achar_membro(d, numero)
    novo = (membro or Membro(entrou_em=d.agora())).model_copy(update={"papel": papel})
    d.repo.salvar_membro(chave, novo)
    return novo


async def _papel(
    d: Deps,
    sessao: Sessao,
    autor: Autor,
    comando: str,
    argumento: str,
    eh_dono: Callable[[str], bool],
) -> Sessao:
    """`!teacher`/`!student`: só um professor da turma ou o dono. Para qualquer outra pessoa o
    comando não existe: responde como a qualquer outro texto fora de comando (a ajuda)."""
    quem = await bloq(d.repo.obter_membro, autor.numero)
    pode = eh_dono(autor.numero) or (quem is not None and quem.papel == "professor")
    if not pode:
        await d.conversa.enviar(messages.ajuda_do_grupo(d.p))
        return sessao
    alvos = _alvos(autor, argumento)
    if not alvos:
        await d.conversa.enviar(messages.papel_uso(comando, d.p))
        return sessao
    papel: Papel = "professor" if _PAPEIS[comando] == "professor" else "aluno"
    for numero in alvos:
        membro = await bloq(_definir_papel, d, numero, papel)
        await d.conversa.enviar(messages.papel_alterado(membro.nome, papel))
    return sessao


# --- !group -----------------------------------------------------------------------------------


async def _perfil_do_grupo(d: Deps, perfil: Profile) -> None:
    entradas = await bloq(d.repo.listar_entradas)
    membros = await bloq(d.repo.listar_membros)
    respostas = await bloq(d.repo.listar_respostas)
    por_autor: dict[str, int] = {}
    for r in respostas:
        por_autor[r.autor_id] = por_autor.get(r.autor_id, 0) + 1

    linhas: list[tuple[str, str, int]] = []
    sem_nome = 0
    for numero, membro in membros:
        if membro.nome:
            nome = membro.nome
        else:
            sem_nome += 1
            nome = f"Student {sem_nome}"
        linhas.append((nome, membro.papel, por_autor.get(numero, 0)))

    if perfil.lembretes_por_dia == 0:
        lembretes = f"off — turn them on with {d.cmd_lembretes} 3"
    else:
        vezes = "once" if perfil.lembretes_por_dia == 1 else f"{perfil.lembretes_por_dia}x"
        lembretes = f"every day, {vezes} between {perfil.janela_inicio}h and {perfil.janela_fim}h"
        proximo = proximo_a_exibir(perfil, d.agora(), d.fuso)
        if proximo is not None:
            lembretes += f"\n⏭️ Next reminder: {messages._quando(proximo, d.agora())}"

    await d.conversa.enviar(
        messages.grupo_perfil(
            nivel=perfil.nivel,
            total=len(entradas),
            praticadas=sum(1 for e in entradas if e.status == "praticada"),
            para_revisar=sum(1 for e in entradas if vencida(e, d.agora())),
            lembretes=lembretes,
            membros=linhas,
        )
    )
