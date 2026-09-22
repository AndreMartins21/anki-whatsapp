"""Todo texto voltado ao usuário fica neste módulo (M9: em inglês — só a linha 🇧🇷, com a
tradução literal, fica em português do Brasil).

Formatação do WhatsApp (`*bold*`, `_italic_`), emojis com moderação e, sempre que possível, um
único texto por resposta: explicação ou avaliação mais o menu (seção 5.5 da spec).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import (
    Entry,
    Evaluation,
    Expansion,
    NivelUsuario,
    Sense,
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
SEM_EXPORTAVEIS = "There's nothing new to export. Use */export all* to export everything again."

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
/list — your words
/pending — the ones you haven't practiced yet
/practice [word] — practice one (no word: the oldest pending one)
/export — generate the Anki file (*/export all* includes the ones already exported)
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
        f"Practice it any time with /praticar {palavra}, or see everything with /lista.",
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
    marca = "✅" if e.status == "praticada" else "🆕"
    return f"{marca} {e.palavra} — {e.sentido.traducao}"


def lista(entradas: Sequence[Entry]) -> str:
    corpo = "\n".join(_linha_de_entrada(e) for e in entradas)
    return f"📚 *Your words* ({len(entradas)})\n{corpo}"


def pendentes(entradas: Sequence[Entry]) -> str:
    corpo = "\n".join(f"• {e.palavra} — {e.sentido.traducao}" for e in entradas)
    return f"🆕 *Pending* ({len(entradas)})\n{corpo}\n\nUse /practice to start with the oldest one."


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


def exportacao(link: str, quantidade: int, ignoradas: int = 0) -> str:
    cartoes = "1 card" if quantidade == 1 else f"{quantidade} cards"
    texto = (
        f"📦 Done! {cartoes} in the Anki file (the link is valid for 24 h):\n{link}\n\n"
        "In Anki: *File → Import* and pick the downloaded file."
    )
    if ignoradas:
        texto += (
            f"\n\n({ignoradas} word(s) were left out for having no usable sentence — "
            "practice them or ask for examples and export again.)"
        )
    return texto
