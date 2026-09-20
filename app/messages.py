"""Todo texto voltado ao usuário (PT-BR, tom amigável e curto) fica neste módulo.

Formatação do WhatsApp (`*negrito*`, `_itálico_`), emojis com moderação e, sempre que possível, um
único texto por resposta: explicação ou avaliação mais o menu (seção 5.5 da spec).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import (
    Entry,
    Evaluation,
    Expansion,
    ModoPratica,
    NivelUsuario,
    Sense,
    SentidoSalvo,
    Veredito,
)

MIDIA_NAO_SUPORTADA = "📎 Por enquanto eu só entendo *texto* — me manda a palavra escrita? 🙂"
ERRO_INESPERADO = "⚠️ Deu ruim aqui do meu lado. Tenta de novo em instantes?"
ERRO_IA = "🤖 Não consegui falar com a IA agora. Tenta de novo em instantes?"
CANCELADO = "Tudo bem, parei por aqui. O que já estava salvo continua salvo. Manda outra palavra quando quiser!"
ENCERRADO = "Beleza! Manda outra palavra quando quiser. 🙂"
COMANDO_DESCONHECIDO = "Não conheço esse comando. Manda /ajuda para ver os que eu tenho."
SEM_ENTRADAS = "Você ainda não tem palavras salvas. Manda uma palavra em inglês para começar!"
SEM_PENDENTES = "Nenhuma palavra pendente. 🎉"
EXPORTACAO_INDISPONIVEL = "A exportação ainda não está disponível por aqui."
SEM_EXPORTAVEIS = "Não há nada novo para exportar. Use */exportar tudo* para exportar tudo de novo."

_NUMEROS = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}

_CABECALHO_VEREDITO: dict[Veredito, str] = {
    "correta": "✅ *Perfeita!*",
    "correta_pouco_natural": "👍 *Correta, mas soa pouco natural.*",
    "quase": "⚠️ *Quase lá!*",
    "incorreta": "❌ *Ainda não.*",
}

AJUDA = """*Como eu funciono* 🤓
Manda uma palavra ou expressão em inglês (pode incluir a frase onde você a viu: `stall | the talks stalled`). Eu explico, você pratica escrevendo uma frase, e eu avalio.

*Comandos*
/lista — suas palavras
/pendentes — as que ainda não praticou
/praticar [palavra] — pratica uma (sem palavra, a pendente mais antiga)
/exportar — gera o arquivo do Anki (*/exportar tudo* inclui as já exportadas)
/apagar palavra — remove uma palavra
/nivel B1-B2 — muda o nível (A2-B1, B1-B2 ou B2-C1)
/cancelar — para o que estava fazendo (nada é apagado)
/status — como estão as coisas"""


def sem_marcas(frase: str) -> str:
    """Tira os [[ ]] que marcam a palavra-alvo — no WhatsApp a frase vai limpa."""
    return frase.replace("[[", "").replace("]]", "")


def _linha_de_opcoes(opcoes: Sequence[str]) -> str:
    return "  ·  ".join(f"{_NUMEROS[i]} {texto}" for i, texto in enumerate(opcoes, start=1))


def _lista_de_opcoes(opcoes: Sequence[str]) -> str:
    return "\n".join(f"{_NUMEROS[i]} {texto}" for i, texto in enumerate(opcoes, start=1))


# ---- menus (também usados para reenviar o menu atual) -----------------------------------------


def menu_escolha(palavra: str, modo: ModoPratica) -> str:
    if modo == "producao_primeiro":
        return menu_producao(palavra)
    return (
        "O que você quer fazer?\n"
        + _lista_de_opcoes(["Escrever uma frase", "Ver exemplos", "Só salvar"])
        + f'\n_(ou já mande sua frase com "{palavra}")_'
    )


def menu_producao(palavra: str) -> str:
    return f"Escreve uma frase com *{palavra}* ✍️\n" + _linha_de_opcoes(
        ["Me dá um exemplo", "Só salvar"]
    )


def menu_pedir_frase(palavra: str) -> str:
    return f"Manda a sua frase com *{palavra}* ✍️"


def menu_proximo() -> str:
    return _linha_de_opcoes(["Outra frase", "Exemplos", "Concluir"])


def menu_apos_exemplos() -> str:
    return "Agora tenta a sua! 💪\n" + _linha_de_opcoes(["Escrever uma frase", "Concluir"])


def menu_sentidos(palavra: str, sentidos: Sequence[Sense]) -> str:
    opcoes = [f"{s.traducao} — {s.definicao}" for s in sentidos]
    return f"Qual sentido de *{palavra}* você quer praticar?\n{_lista_de_opcoes(opcoes)}\n_(responde com o número)_"


def menu_nova_palavra(texto: str) -> str:
    return f'"{texto}" parece uma palavra nova. O que eu faço?\n' + _lista_de_opcoes(
        [f"Praticar *{texto}* agora (salvo a anterior)", "Era minha frase"]
    )


def menu_expansoes(expansoes: Sequence[Expansion]) -> str:
    linhas = "\n".join(
        f"{i}. *{e.expressao}* — {e.traducao} _({e.tipo.replace('_', ' ')})_"
        for i, e in enumerate(expansoes, start=1)
    )
    return f"{linhas}\n_Responde com os números (ex.: 1,3) ou 0 para pular._"


def menu_praticar_expansao() -> str:
    return _linha_de_opcoes(["Praticar agora", "Depois"])


# ---- respostas dos fluxos ------------------------------------------------------------------


def _titulo(palavra: str, classe: str, cefr: str) -> str:
    return f"*{palavra.upper()}* ({classe}) · {cefr}"


def explicacao(
    palavra: str,
    classe: str,
    cefr: str,
    sentido: Sense | SentidoSalvo,
    dica: str,
    modo: ModoPratica,
) -> str:
    linhas = [_titulo(palavra, classe, cefr), f"🇧🇷 {sentido.traducao}", f"📖 {sentido.definicao}"]
    if dica:
        linhas.append(f"💡 {dica}")
    return "\n".join(linhas) + "\n\n" + menu_escolha(palavra, modo)


def escolha_de_sentido(palavra: str, classe: str, cefr: str, sentidos: Sequence[Sense]) -> str:
    return (
        f"{_titulo(palavra, classe, cefr)}\nEsse termo tem mais de um sentido comum.\n\n"
        + menu_sentidos(palavra, sentidos)
    )


def avaliacao(ev: Evaluation, traducao_do_sentido: str) -> str:
    cabecalho = _CABECALHO_VEREDITO[ev.veredito]
    if not ev.sentido_correto:
        cabecalho += f" Aqui o sentido é *{traducao_do_sentido}*."
    elif ev.veredito in ("quase", "correta_pouco_natural"):
        cabecalho += " O sentido está certo."
    linhas = [cabecalho]
    linhas += [f"✏️ {correcao}" for correcao in ev.correcoes]
    linhas.append(f"✨ {sem_marcas(ev.versao_natural)}")
    linhas.append(f"💬 {ev.explicacao}")
    return "\n".join(linhas) + "\n\n" + menu_proximo()


def exemplos(palavra: str, traducao: str, frases: Sequence[str]) -> str:
    numeradas = "\n".join(f"{i}. {sem_marcas(f)}" for i, f in enumerate(frases, start=1))
    return f"📝 *Exemplos de {palavra}* ({traducao})\n{numeradas}\n\n" + menu_apos_exemplos()


def pedido_de_frase(palavra: str, modo: ModoPratica) -> str:
    return menu_producao(palavra) if modo == "producao_primeiro" else menu_pedir_frase(palavra)


def salvo_com_expansoes(palavra: str, expansoes: Sequence[Expansion]) -> str:
    return f"💾 *{palavra}* salvo!\n\nQuer praticar algo relacionado?\n" + menu_expansoes(expansoes)


def salvo(palavra: str) -> str:
    return f"💾 *{palavra}* salvo! Manda outra palavra quando quiser. 🙂"


def expansoes_criadas(criadas: int, ja_existiam: int) -> str:
    if criadas == 0:
        return "Essas você já tinha. Manda outra palavra quando quiser. 🙂"
    plural = "entrada nova" if criadas == 1 else "entradas novas"
    extra = f" ({ja_existiam} já existia)" if ja_existiam else ""
    return f"🆕 Criei {criadas} {plural}{extra}.\n\n" + menu_praticar_expansao()


def pergunta_nova_palavra(texto: str) -> str:
    return menu_nova_palavra(texto)


def lembrete(menu: str) -> str:
    return "Não entendi 😅 Escolhe uma das opções:\n\n" + menu


def entrada_invalida(motivo: str | None) -> str:
    detalhe = f" {motivo}" if motivo else ""
    return f"🤔 Isso não parece uma palavra ou expressão em inglês.{detalhe}"


# ---- comandos --------------------------------------------------------------------------------


def _linha_de_entrada(e: Entry) -> str:
    marca = "✅" if e.status == "praticada" else "🆕"
    return f"{marca} {e.palavra} — {e.sentido.traducao}"


def lista(entradas: Sequence[Entry]) -> str:
    corpo = "\n".join(_linha_de_entrada(e) for e in entradas)
    return f"📚 *Suas palavras* ({len(entradas)})\n{corpo}"


def pendentes(entradas: Sequence[Entry]) -> str:
    corpo = "\n".join(f"• {e.palavra} — {e.sentido.traducao}" for e in entradas)
    return (
        f"🆕 *Pendentes* ({len(entradas)})\n{corpo}\n\nUse /praticar para começar pela mais antiga."
    )


def palavra_nao_encontrada(palavra: str) -> str:
    return f'Não achei "{palavra}" nas suas palavras. Use /lista para ver o que você tem.'


def apagada(palavra: str) -> str:
    return f"🗑️ *{palavra}* apagada."


def nivel_atual(nivel: NivelUsuario) -> str:
    return f"Seu nível é *{nivel}*. Para mudar: /nivel B1-B2 (opções: A2-B1, B1-B2, B2-C1)."


def nivel_alterado(nivel: NivelUsuario) -> str:
    return f"✅ Nível ajustado para *{nivel}*."


def nivel_invalido() -> str:
    return "Nível inválido. Use A2-B1, B1-B2 ou B2-C1."


def status(sessao_waha: str, total: int, pendentes_: int) -> str:
    return (
        "*Status*\n"
        f"📡 WhatsApp (WAHA): {sessao_waha}\n"
        f"📚 Palavras: {total}\n"
        f"🆕 Pendentes: {pendentes_}"
    )


def exportacao(link: str, quantidade: int, ignoradas: int = 0) -> str:
    texto = (
        f"📦 Pronto! {quantidade} cartões no arquivo do Anki (o link vale por 24 h):\n{link}\n\n"
        "No Anki: *Arquivo → Importar* e escolha o arquivo baixado."
    )
    if ignoradas:
        texto += (
            f"\n\n({ignoradas} palavra(s) ficaram de fora por não terem nenhuma frase — "
            "pratique ou peça exemplos e exporte de novo.)"
        )
    return texto
