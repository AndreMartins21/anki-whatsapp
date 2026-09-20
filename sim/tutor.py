"""SimTutor: respostas de IA fabricadas, para o simulador rodar o ciclo sem rede nem credencial.

Não avalia inglês de verdade — só o bastante para percorrer todos os estados. Use `--real-llm`
para conversar com o Gemini.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.choices import contem_palavra_alvo, marcar_alvo
from app.domain.models import (
    Evaluation,
    Expansion,
    Explanation,
    NivelUsuario,
    Sense,
    SentidoSalvo,
)

_NOTA_DO_SIMULADOR = "Resposta simulada — use --real-llm para uma avaliação de verdade."


class SimTutor:
    def explain(self, texto: str, nivel: NivelUsuario) -> Explanation:
        palavra_bruta, _, frase = texto.partition("|")
        palavra = palavra_bruta.strip().lower()
        if not palavra:
            return Explanation(ok=False, motivo_erro="Manda uma palavra em inglês.")

        frase = frase.strip()
        if palavra == "stall":
            sentidos = [
                Sense(
                    id="s1",
                    traducao="travar, emperrar",
                    definicao="to stop making progress",
                    exemplo_curto="the talks stalled",
                ),
                Sense(
                    id="s2",
                    traducao="enrolar",
                    definicao="to delay on purpose",
                    exemplo_curto="stop stalling and answer me",
                ),
            ]
            # Com frase de contexto o sentido já está definido; sem ela, o bot pergunta.
            sentido_do_contexto = "s1" if frase else None
        else:
            sentidos = [
                Sense(
                    id="s1",
                    traducao=f"significado de {palavra} (simulado)",
                    definicao=f"the meaning of {palavra}",
                    exemplo_curto=f"an example with {palavra}",
                )
            ]
            sentido_do_contexto = None
        return Explanation(
            ok=True,
            palavra=palavra,
            classe="verbo",
            cefr_estimado="B2",
            sentidos=sentidos,
            sentido_do_contexto=sentido_do_contexto,
            frase_contexto=(marcar_alvo(frase, palavra) or frase) if frase else None,
            nota=_NOTA_DO_SIMULADOR,
            tags=["trabalho"],
        )

    def evaluate(
        self, palavra: str, sentido: SentidoSalvo | Sense, frase: str, nivel: NivelUsuario
    ) -> Evaluation:
        usa = contem_palavra_alvo(frase, palavra)
        return Evaluation(
            usa_palavra_alvo=usa,
            sentido_correto=usa,
            veredito="correta" if usa else "incorreta",
            correcoes=[],
            versao_natural=marcar_alvo(frase, palavra) or f"[[{palavra}]]",
            explicacao=_NOTA_DO_SIMULADOR,
        )

    def examples(
        self, palavra: str, sentido: SentidoSalvo | Sense, nivel: NivelUsuario, n: int = 3
    ) -> list[str]:
        modelos = [
            "We had to [[{p}]] before the deadline.",
            "She didn't want to [[{p}]] in front of the client.",
            "It's easy to [[{p}]] when nobody is watching.",
        ]
        return [modelo.format(p=palavra) for modelo in modelos[:n]]

    def expansions(
        self,
        palavra: str,
        sentido: SentidoSalvo | Sense,
        nivel: NivelUsuario,
        ja_existentes: Sequence[str],
    ) -> list[Expansion]:
        candidatas = [
            Expansion(expressao=f"{palavra} for time", traducao="ganhar tempo", tipo="colocacao"),
            Expansion(expressao=f"{palavra} out", traducao="parar de vez", tipo="phrasal_verb"),
            Expansion(expressao=f"a big {palavra}", traducao="um grande exemplo", tipo="colocacao"),
            Expansion(expressao=f"{palavra} again", traducao="de novo", tipo="expressao"),
        ]
        existentes = {e.lower() for e in ja_existentes}
        return [c for c in candidatas if c.expressao.lower() not in existentes]
