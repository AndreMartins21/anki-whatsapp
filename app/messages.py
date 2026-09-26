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
    LinhaDaMusica,
    NivelUsuario,
    OpcaoDeMusica,
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
USO_DO_LISTEN = "Tell me which word: /listen 3 (the number from /list) or /listen stall."
ERRO_AUDIO = "🔊 I couldn't make the audio right now. Try again in a bit?"
PAGINA_INVALIDA = "That page doesn't exist. Use /list to see the first one."


def pagina_invalida(p: str = "/") -> str:
    return f"That page doesn't exist. Use {p}list to see the first one."


def sem_entradas(p: str = "/") -> str:
    if p == "/":
        return SEM_ENTRADAS
    return f"The class doesn't have any saved words yet. Add one with {p}add stall."


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
/listen 3 — hear how a word sounds (the word and its example)
/pending — the ones you haven't practiced yet
/practice [word] — practice one (no word: the oldest pending one)
/review — start a review session right now
/song name - artist — practice with a song, line by line
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


def _lista_de_opcoes(opcoes: Sequence[str], grupo: str | None = None) -> str:
    if grupo is not None:  # no grupo, cada opção se responde com o prefixo: !1, !2, !3
        return "\n".join(
            f"{_NUMEROS[i]} {grupo}{i} — {texto}" for i, texto in enumerate(opcoes, start=1)
        )
    return "\n".join(f"{_NUMEROS[i]} {texto}" for i, texto in enumerate(opcoes, start=1))


# ---- menu único (M9) -------------------------------------------------------------------------


def convite(palavra: str, grupo: str | None = None) -> str:
    if grupo is not None:
        return f"Now, write a sentence using *{palavra}* (start it with {grupo}), or type:"
    return f"Now, you can write one or more sentences using *{palavra}*, or type:"


def menu_acoes(palavra: str, *, ja_viu_sinonimos: bool = False, grupo: str | None = None) -> str:
    """`grupo` é o prefixo do grupo (M16); `None` no privado, que segue exatamente como era."""
    sinonimos = "See more synonyms" if ja_viu_sinonimos else "Check synonyms"
    opcoes = [
        "Hear how it sounds 🔊",
        "See more examples",
        sinonimos,
        "Just save",
        "Ignore this word, try another",
    ]
    return convite(palavra, grupo) + "\n" + _lista_de_opcoes(opcoes, grupo)


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
    grupo: str | None = None,
) -> str:
    linhas = [_titulo(palavra, classe, cefr), f"🇧🇷 {sentido.traducao}", f"📖 {sentido.definicao}"]
    if dica:
        linhas.append(f"💡 {dica}")
    if exemplo:
        linhas.append(f'"{sem_marcas(exemplo)}"')
    return (
        "\n".join(linhas)
        + "\n\n"
        + menu_acoes(palavra, ja_viu_sinonimos=ja_viu_sinonimos, grupo=grupo)
    )


def ja_existe(
    palavra: str,
    classe: str,
    cefr: str,
    sentido: Sense | SentidoSalvo,
    exemplo: str,
    *,
    grupo: str | None = None,
) -> str:
    """O aluno mandou uma palavra que já está na lista: avisa, mostra o que já tem e oferece só o
    que faz sentido (frase, exemplos, sinônimos) — salvar já não se aplica, e 0/skip abre caminho
    para outra palavra sem passar pela IA."""
    p = grupo or ""
    linhas = [
        f"📌 You already have *{palavra}* in your list.",
        "",
        _titulo(palavra, classe, cefr),
        f"🇧🇷 {sentido.traducao}",
        f"📖 {sentido.definicao}",
    ]
    if exemplo:
        linhas.append(f'"{sem_marcas(exemplo)}"')
    opcoes = ["Hear how it sounds 🔊", "See more examples", "Check synonyms"]
    return (
        "\n".join(linhas)
        + "\n\n"
        + convite(palavra, grupo)
        + "\n"
        + _lista_de_opcoes(opcoes, grupo)
        + f"\n\nTo send another word or command, type {p}0 or {p}skip."
    )


def palavra_descartada(palavra: str) -> str:
    return f"🗑️ Ignored *{palavra}*, it's not in your list. Send me another word whenever you want!"


def palavra_mantida(palavra: str) -> str:
    return f"Alright, *{palavra}* stays in your list. Send me another word whenever you want!"


def avaliacao(
    ev: Evaluation,
    traducao_do_sentido: str,
    palavra: str,
    *,
    ja_viu_sinonimos: bool = False,
    grupo: str | None = None,
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
        palavra, ja_viu_sinonimos=ja_viu_sinonimos, grupo=grupo
    )


def exemplos(
    palavra: str,
    traducao: str,
    frases: Sequence[str],
    *,
    ja_viu_sinonimos: bool = False,
    grupo: str | None = None,
) -> str:
    numeradas = "\n".join(f"{i}. {sem_marcas(f)}" for i, f in enumerate(frases, start=1))
    return (
        f"📝 *Examples with {palavra}* ({traducao})\n{numeradas}\n\n"
        "Want to try a sentence of your own?\n"
        + menu_acoes(palavra, ja_viu_sinonimos=ja_viu_sinonimos, grupo=grupo)
    )


def sinonimos(
    palavra: str, traducao: str, itens: Sequence[Synonym], *, grupo: str | None = None
) -> str:
    linhas: list[str] = []
    for s in itens:
        linhas.append(f"*{s.expressao}* = {s.significado}")
        linhas.append(f'_Example: "{sem_marcas(s.exemplo)}"_')
    corpo = "\n".join(linhas)
    return (
        f"🔄 *Synonyms for {palavra}* ({traducao})\n{corpo}\n\n"
        f"Want to try a sentence with *{palavra}*?\n"
        + menu_acoes(palavra, ja_viu_sinonimos=True, grupo=grupo)
    )


def salvo(palavra: str, sugestoes: Sequence[Expansion] = (), *, p: str = "/") -> str:
    linhas = [
        f"✅ Saved: *{palavra}*.",
        f"Practice it any time with {p}practice {palavra}, or see everything with {p}list.",
    ]
    if sugestoes:
        itens = ", ".join(f"*{e.expressao}*" for e in sugestoes)
        linhas.append(f"You might like these too: {itens}.")
    if p == "/":
        linhas.append("Send me another word or expression whenever you want.")
    else:  # no grupo, palavra nova entra só por !add
        linhas.append(f"Add another one whenever you want: {p}add word.")
    return "\n".join(linhas)


def resposta_livre(
    resposta: str, palavra: str, *, ja_viu_sinonimos: bool = False, grupo: str | None = None
) -> str:
    return f"{resposta}\n\n" + menu_acoes(palavra, ja_viu_sinonimos=ja_viu_sinonimos, grupo=grupo)


def entrada_invalida(motivo: str | None) -> str:
    detalhe = f" {motivo}" if motivo else ""
    return f"🤔 That doesn't look like an English word or expression.{detalhe}"


# ---- comandos --------------------------------------------------------------------------------


def _linha_de_entrada(e: Entry) -> str:
    return f"{e.palavra}: {e.sentido.traducao}"


def lista(
    pagina: Sequence[tuple[int, Entry]],
    *,
    total: int,
    numero: int,
    paginas: int,
    p: str = "/",
    grupo: bool = False,
) -> str:
    """Uma página da lista, das mais novas para as mais antigas. Cada palavra leva o seu número
    fixo (1 = a mais antiga), o mesmo que `/info`, `/practice` e `/delete` aceitam. No grupo
    (M16) o título é da turma e a dica é de `!practice` (não há `!info` na turma)."""
    corpo = "\n".join(f"{n}. {_linha_de_entrada(e)}" for n, e in pagina)
    titulo = "The class's words" if grupo else "Your words"
    dica = (
        f"{p}practice {pagina[0][0]} to practice one"
        if grupo
        else f"{p}info {pagina[0][0]} for details"
    )
    texto = f"📚 *{titulo}* ({total}) — newest first\n{corpo}\n\n💡 {dica}"
    if paginas > 1:
        proxima = f" — {p}list {numero + 1} for more" if numero < paginas else ""
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


def pronuncia(palavra: str, exemplo: str | None) -> str:
    """O texto que vai junto das notas de voz: o que o aluno está prestes a ouvir."""
    linhas = [f"🔊 *{palavra}*"]
    if exemplo:
        linhas.append(f'"{sem_marcas(exemplo)}"')
    return "\n".join(linhas)


def palavra_nao_encontrada(palavra: str, p: str = "/", *, grupo: bool = False) -> str:
    de_quem = "the class's words" if grupo else "your words"
    return f'I couldn\'t find "{palavra}" in {de_quem}. Use {p}list to see what there is.'


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


def _palavras(quantidade: int) -> str:
    return "1 word" if quantidade == 1 else f"{quantidade} words"


def exportacao(quantidade: int) -> str:
    """Legenda do arquivo enviado direto pelo WhatsApp."""
    return (
        f"📊 Done! {_palavras(quantidade)} in the spreadsheet. "
        "Tabs: *Words*, *Sentences* and *Synonyms*."
    )


def exportacao_com_link(link: str, quantidade: int) -> str:
    """Plano B, quando o WhatsApp não aceitou o arquivo."""
    return (
        f"📊 Done! {_palavras(quantidade)} in the spreadsheet. I couldn't send the file here, "
        f"so here's a link (valid for 24 h):\n{link}\n\n"
        "Tabs: *Words*, *Sentences* and *Synonyms*."
    )


# ---- revisão espaçada e lembretes (seção 5.7, M10) ---------------------------------------------

SEM_NADA_PARA_REVISAR = "No pending reviews right now. 🎉"
DICA_DE_LEMBRETES = "\n\n💡 Want daily practice reminders? Send /reminders 3"
LEMBRETES_INVALIDOS = (
    "I couldn't understand that. Try /reminders 3 (3 times a day, 9h-21h) or "
    "/reminders 3 9h-22h (your own window), or /reminders off."
)


def dica_de_lembretes(cmd: str = "/reminders") -> str:
    return f"\n\n💡 Want daily practice reminders? Send {cmd} 3"


def lembretes_invalidos(cmd: str = "/reminders") -> str:
    return (
        f"I couldn't understand that. Try {cmd} 3 (3 times a day, 9h-21h) or "
        f"{cmd} 3 9h-22h (your own window), or {cmd} off."
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


def card_de_revisao(
    indice: int,
    total: int,
    palavra: str,
    *,
    grupo: str | None = None,
    marcado: str | None = None,
) -> str:
    """`marcado` (M17) é o número de quem responde este card no grupo: o texto leva `@numero` e
    quem envia passa o número em `mentions`."""
    if grupo is not None and marcado is not None:
        return (
            f"🔁 {indice}/{total} · *{palavra}*\n"
            f"@{marcado}, your turn: explain it in English in your own words, or write a "
            f"sentence using it (start with {grupo}).\n"
            f"_Anyone can type {grupo}0 to leave the practice._"
        )
    if grupo is not None:
        return (
            f"🔁 {indice}/{total} · *{palavra}*\n"
            f"Explain it in English in your own words, or write a sentence using it "
            f"(start with {grupo}).\n"
            f"_Type {grupo}0 to leave the practice._"
        )
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


def revisao_encerrada(feitas: Sequence[str], lapsos: Sequence[str], *, p: str = "/") -> str:
    if not feitas:
        return SEM_NADA_PARA_REVISAR
    solidas = [palavra for palavra in feitas if palavra not in lapsos]
    linhas = [f"🎉 *Practice done* — {len(feitas)} reviewed."]
    if solidas:
        linhas.append(f"✅ Solid: {', '.join(solidas)}")
    if lapsos:
        linhas.append(f"🔁 Coming back soon: {', '.join(lapsos)}")
    if p == "/":
        linhas.append("Send me a new word or expression whenever you want.")
    else:  # no grupo, palavra nova entra só por !add
        linhas.append(f"Add a new word whenever you want: {p}add word.")
    return "\n".join(linhas)


def _proximo(proximo: datetime | None, agora: datetime | None) -> str:
    return f" Next one: {_quando(proximo, agora)}." if proximo and agora else ""


def lembretes_atuais(
    perfil: Profile,
    proximo: datetime | None = None,
    agora: datetime | None = None,
    cmd: str = "/reminders",
) -> str:
    if perfil.lembretes_por_dia == 0:
        return (
            f"Reminders are off. Turn them on with {cmd} 3 (or {cmd} 3 9h-22h for your own window)."
        )
    vezes = "once a day" if perfil.lembretes_por_dia == 1 else f"{perfil.lembretes_por_dia}x a day"
    return (
        f"Reminders: {vezes}, between {perfil.janela_inicio}h and {perfil.janela_fim}h."
        f"{_proximo(proximo, agora)} "
        f"Change with {cmd} N or turn off with {cmd} off."
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


# --- Prática com música (M13, seção 5.8) ---

SONG_USO = (
    "Tell me the song: /song paper plane — or add the artist to narrow it down: "
    "/song paper plane - the inventors"
)
SONG_INDISPONIVEL = "Song practice isn't available here yet."
SONG_BUSCA_FALHOU = "I couldn't reach the lyrics library right now. Try again in a bit?"
SONG_SEM_VERSOS = "I found the song, but its lyrics are empty here. Try another one: /song name"
SONG_DESCARTADAS = "OK, nothing saved. Send me a new word or /song whenever you want."
SAIR_DA_PRATICA = "_Type 0 to leave the practice._"

_COMPREENSAO_EMOJI = {"entendeu": "✅", "parcial": "🤔", "nao_entendeu": "❌"}


def song_nao_encontrada(busca: str, fora_do_ingles: bool) -> str:
    if fora_do_ingles:
        return (
            f"I found *{busca}*, but the lyrics aren't in English — and we can't practice "
            "English with a song in another language. Send me another one: /song name"
        )
    return f"I couldn't find *{busca}*. Check the spelling, or add the artist: /song name - artist"


def song_candidatas(opcoes: Sequence[OpcaoDeMusica], *, invalida: bool = False) -> str:
    cabecalho = (
        "Pick one of the numbers below." if invalida else "I found more than one. Which one is it?"
    )
    linhas = [cabecalho]
    linhas += [f"{i}. *{o.titulo}* — {o.artista}" for i, o in enumerate(opcoes, start=1)]
    linhas.append(
        "Reply with the number, or 0 to cancel. Not here? Send the name with the artist: "
        "paper plane - the inventors"
    )
    return "\n".join(linhas)


def song_verso(indice: int, total: int, verso: str) -> str:
    return (
        f"🎵 Line {indice}/{total}\n"
        f"_{verso}_\n"
        "What does it mean? Explain in English or Portuguese.\n"
        f"{SAIR_DA_PRATICA}"
    )


def song_inicio(titulo: str, artista: str, total: int, verso: str) -> str:
    linhas = "line" if total == 1 else "lines"
    return (
        f"🎶 *{titulo}* — {artista}\n"
        f"Let's go line by line ({total} {linhas}, repeated ones skipped): tell me what each "
        "line means, and I'll give you feedback.\n\n" + song_verso(1, total, verso)
    )


def feedback_de_verso(linha: LinhaDaMusica) -> str:
    partes = [f"{_COMPREENSAO_EMOJI[linha.compreensao]} {linha.feedback}"]
    if linha.significado:
        partes.append(f"💬 {linha.significado}")
    return "\n".join(partes)


def song_resumo(titulo: str, feitas: int, total: int, expressoes: Sequence[str]) -> str:
    linhas = [f"🎉 *{titulo}* — you went through {feitas} of {total} lines."]
    if not expressoes:
        linhas.append("Send me a new word, or /song for another one, whenever you want.")
        return "\n".join(linhas)
    linhas.append("Words and expressions you may want to keep:")
    linhas += [f"{i}. {e}" for i, e in enumerate(expressoes, start=1)]
    linhas.append(
        "Want me to save them in your dictionary? Reply with the numbers (e.g. 1 3), *all*, "
        "or 0 to skip."
    )
    return "\n".join(linhas)


def song_numeros_invalidos(expressoes: Sequence[str]) -> str:
    linhas = ["Pick numbers from the list:"]
    linhas += [f"{i}. {e}" for i, e in enumerate(expressoes, start=1)]
    linhas.append("Reply with the numbers (e.g. 1 3), *all*, or 0 to skip.")
    return "\n".join(linhas)


def song_salvas(palavras: Sequence[str]) -> str:
    if not palavras:
        return "I couldn't save those, sorry. Send me any of them as a new word to try again."
    return (
        f"✅ Saved to your dictionary: {', '.join(palavras)}. They're in /pending — practice "
        "them whenever you want."
    )


# --- Controle de acesso (M15, ADR-0018) -------------------------------------------------------


def sem_plano(email: str) -> str:
    """Para quem não está na lista e escreve no privado (no máximo uma vez a cada 7 dias)."""
    return (
        "You don't have a plan with this bot yet. To use it, email "
        f"{email} asking for access.\n"
        f"🇧🇷 Você não possui um plano com o nosso bot. Para usá-lo, contate {email} "
        "solicitando acesso."
    )


def grupo_ativado(p: str = "!") -> str:
    return f"✅ I'm active in this group now. Send {p}help to see what I can do."


GRUPO_ATIVADO = grupo_ativado()
GRUPO_JA_ATIVO = "I'm already active in this group. 🙂"
GRUPO_DESATIVADO = "OK, I'll stay quiet in this group from now on. Your words are still saved."


def grupo_limite(maximo: int) -> str:
    return (
        f"I can be active in up to {maximo} groups at a time, and that limit is reached. "
        "Turn one off first (/groups in a private chat)."
    )


ADMIN_USO = "Use /admin add 5531999998888 or /admin remove 5531999998888 (digits only, with country and area code)."
ADMIN_JA_E_ADMIN = "That number is already an admin."
ADMIN_NAO_E_ADMIN = "That number isn't an admin."
ADMIN_E_O_DONO = "That's the owner — the owner is always an admin."


def admin_adicionado(p: str = "!") -> str:
    return f"✅ Added as an admin. They can activate me in a group with {p}activate."


ADMIN_ADICIONADO = admin_adicionado()
ADMIN_REMOVIDO = "✅ Removed. Groups they already activated stay active."


def admin_lista(numeros: Sequence[str]) -> str:
    linhas = [f"👑 *Admins* ({len(numeros) + 1})", "• you (owner)"]
    linhas += [f"• {n}" for n in numeros]
    linhas.append("Add one with /admin add 5531999998888.")
    return "\n".join(linhas)


GRUPOS_USO = "Use /groups to see the groups, or /groups off 1 to turn one off."
GRUPO_NAO_EXISTE = "There's no active group with that number. Use /groups to see them."


def grupo_desligado(nome: str | None) -> str:
    return f"✅ Turned off: {nome or 'that group'}. Its words are still saved."


def grupos(
    ativos: Sequence[str | None],
    fixos: Sequence[str | None],
    pendentes: Sequence[tuple[str | None, int]],
    maximo: int,
    p: str = "!",
) -> str:
    """`ativos`: nomes dos grupos ativados por comando (numerados); `fixos`: os de ALLOWED_GROUPS;
    `pendentes`: (nome, horas até eu sair) dos grupos em que ainda ninguém digitou !activate."""
    if not ativos and not fixos and not pendentes:
        return f"I'm not in any group yet. Add me to one and send {p}activate there."
    linhas: list[str] = []
    if ativos or fixos:
        linhas.append(f"🏫 *Active groups* ({len(ativos)}/{maximo})")
        linhas += [f"{i}. {nome or '(no name)'}" for i, nome in enumerate(ativos, start=1)]
        linhas += [f"• {nome or '(no name)'} (fixed in the config)" for nome in fixos]
    if pendentes:
        linhas.append(f"⏳ *Waiting for a {p}activate* (I leave when the time runs out)")
        linhas += [f"• {nome or '(no name)'} — {horas}h left" for nome, horas in pendentes]
    if ativos:
        linhas.append("Turn one off with /groups off 1.")
    return "\n".join(linhas)


# --- Grupo (M16, ADR-0019) ---------------------------------------------------------------------


def ajuda_do_grupo(p: str = "!") -> str:
    """Só os comandos do grupo: nunca cita os do privado."""
    return (
        "*How I work in this group* 🏫\n"
        f"I only read messages that start with {p}. The rest is your chat, and I don't read it.\n\n"
        "*Commands*\n"
        f"{p}add word — add a word or expression (with context: {p}add stall | the talks stalled)\n"
        f"{p}list [page] — the class's words, numbered\n"
        f"{p}practice [word or number] — practice one (no word: the oldest pending one)\n"
        f"{p}review — start a review round right now\n"
        f"{p}reminder 3 9h-22h — daily practice reminders (or {p}reminder off)\n"
        f"{p}group — the class, its words and reminders\n\n"
        f"While practicing, pick an option with {p}1, {p}2 or {p}3, and start a sentence with {p} "
        "to try it."
    )


def grupo_add_uso(p: str = "!") -> str:
    return (
        f"Tell me which word: {p}add stall — or with the sentence where you saw it: "
        f"{p}add stall | the talks stalled."
    )


def nova_palavra_no_grupo(p: str = "!") -> str:
    return f"To add a new word to the class, use {p}add word (for example {p}add stall)."


def papel_alterado(nome: str | None, papel: str) -> str:
    quem = nome or "That person"
    return f"✅ {quem} is now a {'teacher' if papel == 'professor' else 'student'}."


def papel_uso(comando: str, p: str = "!") -> str:
    return f"Tell me who: {p}{comando} 5531999998888 (digits only, with country and area code)."


def grupo_perfil(
    *,
    nivel: str,
    total: int,
    praticadas: int,
    para_revisar: int,
    lembretes: str,
    membros: Sequence[tuple[str, str, int]],
) -> str:
    """`!group`: a turma. `membros` é (nome, papel, respostas na revisão); só nomes, nunca
    telefones, e sem menção (não notifica ninguém)."""
    linhas = [
        "*Your class* 🏫",
        f"🎯 Level: {nivel}",
        f"📚 Words: {total} ({praticadas} practiced, {total - praticadas} pending)",
        f"🔁 Due for review: {para_revisar}",
        f"⏰ Reminders: {lembretes}",
    ]
    if membros:
        linhas.append(f"👥 *Members* ({len(membros)})")
        for nome, papel, respostas in membros:
            rotulo = "teacher" if papel == "professor" else "student"
            extra = f" · {respostas} review answers" if respostas else ""
            linhas.append(f"• {nome} ({rotulo}){extra}")
    else:
        linhas.append("👥 Nobody has used me here yet.")
    return "\n".join(linhas)


# --- Revisão em grupo (M17, ADR-0020) ----------------------------------------------------------


def grupo_sem_aluno(p: str = "!") -> str:
    return (
        "I couldn't find anyone to tag for a review. Teachers are never tagged, so I need at "
        f"least one student in the group (they can say {p}help to make sure I know them)."
    )


def feedback_sem_nota(rev: Revisao) -> str:
    """Resposta de quem NÃO é a pessoa marcada: feedback, mas o card e a nota não mudam."""
    return (
        "💬 Nice try — this one doesn't count, the card is for the person I tagged.\n"
        + feedback_de_revisao(rev)
    )


def repasse(indice: int, total: int, palavra: str, marcado: str, p: str = "!") -> str:
    return (
        "⏰ No answer yet, so I'm passing this one on.\n"
        f"🔁 {indice}/{total} · *{palavra}*\n"
        f"@{marcado}, your turn: explain it in English or write a sentence using it "
        f"(start with {p})."
    )


def revisao_sem_resposta(feitas: Sequence[str], lapsos: Sequence[str], *, p: str = "!") -> str:
    """A rodada fechou porque ninguém respondeu a tempo."""
    if not feitas:
        return "😴 Nobody answered in time, so I closed this review. I'll be back later."
    return "😴 Nobody answered in time, so I closed this review.\n" + revisao_encerrada(
        feitas, lapsos, p=p
    )
