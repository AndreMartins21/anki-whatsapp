"""Todo texto voltado ao usuário fica neste módulo (M9: em inglês — só a linha 🇧🇷, com a
tradução literal, fica em português do Brasil).

Formatação do WhatsApp (`*bold*`, `_italic_`), emojis com moderação e, sempre que possível, um
único texto por resposta: explicação ou avaliação mais o menu (seção 5.5 da spec), ou feedback
mais o próximo card na revisão espaçada (seção 5.7, M10).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from app.domain.models import (
    Entry,
    Evaluation,
    Expansion,
    NivelUsuario,
    Profile,
    Revisao,
    Sense,
    Sentence,
    SentidoSalvo,
    Synonym,
    Veredito,
)

MIDIA_NAO_SUPORTADA = "📎 I can only read *text* for now — can you type the word instead? 🙂"
ERRO_INESPERADO = "⚠️ Something went wrong on my end. Try again in a bit?"
ERRO_IA = "🤖 I couldn't reach the AI right now. Try again in a bit?"
CANCELADO = "No problem, I stopped there. Anything already saved is still saved. Send me another word whenever you want!"
ENCERRADO = "Alright! Send me another word whenever you want. 🙂"
COMANDO_DESCONHECIDO = "I don't know that command. Send /help to see what I have."
SEM_ENTRADAS = "You don't have any saved words yet. Send me an English word to get started!"
SEM_PENDENTES = "No pending words. 🎉"
EXPORTACAO_INDISPONIVEL = "Export isn't available here yet."
SEM_EXPORTAVEIS = "There's nothing to export yet. Send me an English word to get started!"
USO_DO_INFO = "Tell me which word: /info 3 (the number from /list) or /info stall."
PAGINA_INVALIDA = "That page doesn't exist. Use /list to see the first one."

_MAX_FRASES_NO_INFO = 5
_MAX_EXEMPLOS_NO_INFO = 3
_NUMEROS = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}

_CABECALHO_VEREDITO: dict[Veredito, str] = {
    "correta": "✅ *Perfect!*",
    "correta_pouco_natural": "👍 *Correct, but a bit unnatural.*",
    "quase": "⚠️ *Almost there!*",
    "incorreta": "❌ *Not quite.*",
}

AJUDA = """*How I work* 🤓
Send me a word or expression in English (you can include the sentence where you saw it: `stall | the talks stalled`). I'll explain it, you practice writing a sentence, and I'll give you feedback.

*Commands*
/list [page] — your words, numbered
/info 3 — everything about a word (sentences, synonyms…)
/pending — the ones you haven't practiced yet
/practice [word] — practice one (no word: the oldest pending one)
/review — start a review session right now
/reminders 3 9h-22h — daily practice reminders (or /reminders off)
/profile — your level, words and reminders
/export — get an Excel spreadsheet with everything
/delete word — remove a word
/level B1-B2 — change your level (A2-B1, B1-B2 or B2-C1)
/cancel — stop what you were doing (nothing is deleted)
/status — how things are going"""


def sem_marcas(frase: str) -> str:
    """Tira os [[ ]] que marcam a palavra-alvo — no WhatsApp a frase vai limpa."""
    return frase.replace("[[", "").replace("]]", "")


def _linha_de_opcoes(opcoes: Sequence[str]) -> str:
    return "  ·  ".join(f"{_NUMEROS[i]} {texto}" for i, texto in enumerate(opcoes, start=1))


def _lista_de_opcoes(opcoes: Sequence[str]) -> str:
    return "\n".join(f"{_NUMEROS[i]} {texto}" for i, texto in enumerate(opcoes, start=1))


# ---- menu único (M9) -------------------------------------------------------------------------


def convite(palavra: str) -> str:
    return f"Now, you can write one or more sentences using *{palavra}*, or type:"


def menu_acoes(palavra: str, *, ja_viu_sinonimos: bool = False) -> str:
    opcao_2 = "See more synonyms" if ja_viu_sinonimos else "Check synonyms"
    return convite(palavra) + "\n" + _lista_de_opcoes(["See more examples", opcao_2, "Just save"])


# ---- respostas dos fluxos ------------------------------------------------------------------


def _titulo(palavra: str, classe: str, cefr: str) -> str:
    return f"*{palavra}* ({classe}) — {cefr}"


def explicacao(
    palavra: str,
    classe: str,
    cefr: str,
    sentido: Sense | SentidoSalvo,
    dica: str,
    exemplo: str,
    *,
    ja_viu_sinonimos: bool = False,
) -> str:
    linhas = [_titulo(palavra, classe, cefr), f"🇧🇷 {sentido.traducao}", f"📖 {sentido.definicao}"]
    if dica:
        linhas.append(f"💡 {dica}")
    if exemplo:
        linhas.append(f'"{sem_marcas(exemplo)}"')
    return "\n".join(linhas) + "\n\n" + menu_acoes(palavra, ja_viu_sinonimos=ja_viu_sinonimos)


def avaliacao(
    ev: Evaluation, traducao_do_sentido: str, palavra: str, *, ja_viu_sinonimos: bool = False
) -> str:
    cabecalho = _CABECALHO_VEREDITO[ev.veredito]
    if not ev.sentido_correto:
        cabecalho += f" Here the meaning is *{traducao_do_sentido}*."
    elif ev.veredito in ("quase", "correta_pouco_natural"):
        cabecalho += " The meaning is right."
    linhas = [cabecalho]
    linhas += [f"✏️ {correcao}" for correcao in ev.correcoes]
    linhas.append(f"✨ {sem_marcas(ev.versao_natural)}")
    linhas.append(f"💬 {ev.explicacao}")
    corpo = "\n".join(linhas)
    return f"{corpo}\n\nWant to try another sentence?\n" + menu_acoes(
        palavra, ja_viu_sinonimos=ja_viu_sinonimos
    )


def exemplos(
    palavra: str, traducao: str, frases: Sequence[str], *, ja_viu_sinonimos: bool = False
) -> str:
    numeradas = "\n".join(f"{i}. {sem_marcas(f)}" for i, f in enumerate(frases, start=1))
    return (
        f"📝 *Examples with {palavra}* ({traducao})\n{numeradas}\n\n"
        "Want to try a sentence of your own?\n"
        + menu_acoes(palavra, ja_viu_sinonimos=ja_viu_sinonimos)
    )


def sinonimos(palavra: str, traducao: str, itens: Sequence[Synonym]) -> str:
    linhas: list[str] = []
    for s in itens:
        linhas.append(f"*{s.expressao}* = {s.significado}")
        linhas.append(f'_Example: "{sem_marcas(s.exemplo)}"_')
    corpo = "\n".join(linhas)
    return (
        f"🔄 *Synonyms for {palavra}* ({traducao})\n{corpo}\n\n"
        f"Want to try a sentence with *{palavra}*?\n" + menu_acoes(palavra, ja_viu_sinonimos=True)
    )


def salvo(palavra: str, sugestoes: Sequence[Expansion] = ()) -> str:
    linhas = [
        f"✅ Saved: *{palavra}*.",
        f"Practice it any time with /practice {palavra}, or see everything with /list.",
    ]
    if sugestoes:
        itens = ", ".join(f"*{e.expressao}*" for e in sugestoes)
        linhas.append(f"You might like these too: {itens}.")
    linhas.append("Send me another word or expression whenever you want.")
    return "\n".join(linhas)


def resposta_livre(resposta: str, palavra: str, *, ja_viu_sinonimos: bool = False) -> str:
    return f"{resposta}\n\n" + menu_acoes(palavra, ja_viu_sinonimos=ja_viu_sinonimos)


def entrada_invalida(motivo: str | None) -> str:
    detalhe = f" {motivo}" if motivo else ""
    return f"🤔 That doesn't look like an English word or expression.{detalhe}"


# ---- comandos --------------------------------------------------------------------------------


def _linha_de_entrada(e: Entry) -> str:
    return f"{e.palavra}: {e.sentido.traducao}"


def lista(pagina: Sequence[tuple[int, Entry]], *, total: int, numero: int, paginas: int) -> str:
    """Uma página da lista, das mais novas para as mais antigas. Cada palavra leva o seu número
    fixo (1 = a mais antiga), o mesmo que `/info`, `/practice` e `/delete` aceitam."""
    corpo = "\n".join(f"{n}. {_linha_de_entrada(e)}" for n, e in pagina)
    texto = (
        f"📚 *Your words* ({total}) — newest first\n{corpo}\n\n💡 /info {pagina[0][0]} for details"
    )
    if paginas > 1:
        proxima = f" — /list {numero + 1} for more" if numero < paginas else ""
        texto += f"\nPage {numero}/{paginas}{proxima}"
    return texto


def pendentes(entradas: Sequence[Entry]) -> str:
    corpo = "\n".join(f"• {e.palavra} — {e.sentido.traducao}" for e in entradas)
    return f"🆕 *Pending* ({len(entradas)})\n{corpo}\n\nUse /practice to start with the oldest one."


def _data_curta(momento: datetime | None) -> str:
    return f"{momento:%Y-%m-%d}" if momento else "—"


def info(entrada: Entry, numero: int, frases: Sequence[Sentence]) -> str:
    """Tudo o que o bot sabe de uma palavra: sentido, nota, revisão, frases do aluno (já
    corrigidas), exemplos do bot e sinônimos."""
    linhas = [
        f"*{numero}. {entrada.palavra}* ({entrada.classe}) — {entrada.cefr_estimado}",
        f"🇧🇷 {entrada.sentido.traducao}",
        f"📖 {entrada.sentido.definicao}",
    ]
    for outro in entrada.outros_sentidos:
        linhas.append(f"↔️ {outro.traducao} — {outro.definicao}")
    if entrada.nota:
        linhas.append(f"💡 {entrada.nota}")
    situacao = "practiced" if entrada.status == "praticada" else "not practiced yet"
    linhas.append(f"📊 {situacao} · next review: {_data_curta(entrada.proxima_revisao)}")

    do_aluno = _sem_repetir(
        sem_marcas(f.versao_natural or f.texto) for f in reversed(frases) if f.autor == "usuario"
    )
    if do_aluno:
        linhas += ["", "✍️ *Your sentences*", *(f"• {f}" for f in do_aluno[:_MAX_FRASES_NO_INFO])]
    do_bot = _sem_repetir(sem_marcas(f.texto) for f in frases if f.autor == "bot")
    if do_bot:
        linhas += ["", "📝 *Examples*", *(f"• {f}" for f in do_bot[:_MAX_EXEMPLOS_NO_INFO])]
    if entrada.sinonimos:
        linhas += ["", "🔄 *Synonyms*"]
        linhas += [f"• *{s.expressao}* = {s.significado}" for s in entrada.sinonimos]
    return "\n".join(linhas)


def _sem_repetir(frases: Iterable[str]) -> list[str]:
    vistas: set[str] = set()
    unicas: list[str] = []
    for frase in frases:
        chave = frase.strip().casefold()
        if chave and chave not in vistas:
            vistas.add(chave)
            unicas.append(frase.strip())
    return unicas


def _quando(momento: datetime, agora: datetime) -> str:
    """ "today at 14:00", "tomorrow at 08:00" ou "Mon 28 Sep at 08:00" (ambos no fuso do aluno)."""
    dias = (momento.date() - agora.astimezone(momento.tzinfo).date()).days
    dia = "today" if dias == 0 else "tomorrow" if dias == 1 else f"{momento:%a %d %b}"
    return f"{dia} at {momento:%H:%M}"


def perfil_do_aluno(
    p: Profile,
    *,
    total: int,
    praticadas: int,
    para_revisar: int,
    proximo: datetime | None = None,
    agora: datetime | None = None,
) -> str:
    if p.lembretes_por_dia == 0:
        lembretes = "off — turn them on with /reminders 3"
    else:
        vezes = "once" if p.lembretes_por_dia == 1 else f"{p.lembretes_por_dia}x"
        lembretes = f"every day, {vezes} between {p.janela_inicio}h and {p.janela_fim}h"
        if proximo is not None and agora is not None:
            lembretes += f"\n⏭️ Next reminder: {_quando(proximo, agora)}"
    return (
        "*Your profile* 👤\n"
        f"🎯 Level: {p.nivel}\n"
        f"📚 Words: {total} ({praticadas} practiced, {total - praticadas} pending)\n"
        f"🔁 Due for review: {para_revisar}\n"
        f"⏰ Reminders: {lembretes}"
    )


def palavra_nao_encontrada(palavra: str) -> str:
    return f'I couldn\'t find "{palavra}" in your words. Use /list to see what you have.'


def apagada(palavra: str) -> str:
    return f"🗑️ *{palavra}* deleted."


def nivel_atual(nivel: NivelUsuario) -> str:
    return f"Your level is *{nivel}*. To change it: /level B1-B2 (options: A2-B1, B1-B2, B2-C1)."


def nivel_alterado(nivel: NivelUsuario) -> str:
    return f"✅ Level set to *{nivel}*."


def nivel_invalido() -> str:
    return "Invalid level. Use A2-B1, B1-B2 or B2-C1."


def status(sessao_waha: str, total: int, pendentes_: int) -> str:
    return (
        f"*Status*\n📡 WhatsApp (WAHA): {sessao_waha}\n📚 Words: {total}\n🆕 Pending: {pendentes_}"
    )


def exportacao(link: str, quantidade: int) -> str:
    palavras = "1 word" if quantidade == 1 else f"{quantidade} words"
    return (
        f"📊 Done! {palavras} in the spreadsheet (the link is valid for 24 h):\n{link}\n\n"
        "It has three tabs: *Words*, *Sentences* and *Synonyms*."
    )


# ---- revisão espaçada e lembretes (seção 5.7, M10) ---------------------------------------------

SEM_NADA_PARA_REVISAR = "No pending reviews right now. 🎉"
DICA_DE_LEMBRETES = "\n\n💡 Want daily practice reminders? Send /reminders 3"
LEMBRETES_INVALIDOS = (
    "I couldn't understand that. Try /reminders 3 (3 times a day, 9h-21h) or "
    "/reminders 3 9h-22h (your own window), or /reminders off."
)

_QUALIDADE_EMOJI: dict[str, str] = {
    "de_novo": "❌",
    "dificil": "🤔",
    "bom": "✅",
    "facil": "🌟",
}


def hora_da_pratica(total: int) -> str:
    palavra = "word" if total == 1 else "words"
    return f"⏰ *Practice time* — {total} {palavra} to review."


def card_de_revisao(indice: int, total: int, palavra: str) -> str:
    return (
        f"🔁 {indice}/{total} · *{palavra}*\n"
        "Explain it in English in your own words, or write a sentence using it.\n"
        "_Type 0 to leave the practice._"
    )


def feedback_de_revisao(rev: Revisao) -> str:
    linhas = [f"{_QUALIDADE_EMOJI[rev.qualidade]} {rev.feedback}"]
    if rev.correcao:
        linhas.append(f"💬 {rev.correcao}")
    return "\n".join(linhas)


def revisao_encerrada(feitas: Sequence[str], lapsos: Sequence[str]) -> str:
    if not feitas:
        return SEM_NADA_PARA_REVISAR
    solidas = [palavra for palavra in feitas if palavra not in lapsos]
    linhas = [f"🎉 *Practice done* — {len(feitas)} reviewed."]
    if solidas:
        linhas.append(f"✅ Solid: {', '.join(solidas)}")
    if lapsos:
        linhas.append(f"🔁 Coming back soon: {', '.join(lapsos)}")
    linhas.append("Send me a new word or expression whenever you want.")
    return "\n".join(linhas)


def _proximo(proximo: datetime | None, agora: datetime | None) -> str:
    return f" Next one: {_quando(proximo, agora)}." if proximo and agora else ""


def lembretes_atuais(
    perfil: Profile, proximo: datetime | None = None, agora: datetime | None = None
) -> str:
    if perfil.lembretes_por_dia == 0:
        return (
            "Reminders are off. Turn them on with /reminders 3 (or /reminders 3 9h-22h for "
            "your own window)."
        )
    vezes = "once a day" if perfil.lembretes_por_dia == 1 else f"{perfil.lembretes_por_dia}x a day"
    return (
        f"Reminders: {vezes}, between {perfil.janela_inicio}h and {perfil.janela_fim}h."
        f"{_proximo(proximo, agora)} "
        "Change with /reminders N or turn off with /reminders off."
    )


def lembretes_alterados(
    perfil: Profile, proximo: datetime | None = None, agora: datetime | None = None
) -> str:
    vezes = "once a day" if perfil.lembretes_por_dia == 1 else f"{perfil.lembretes_por_dia}x a day"
    return (
        f"✅ Reminders set: {vezes}, between {perfil.janela_inicio}h and {perfil.janela_fim}h."
        f"{_proximo(proximo, agora)}"
    )


def lembretes_desligados() -> str:
    return "✅ Reminders are off."
