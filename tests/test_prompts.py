"""Os prompts de explicar (M31, ADR-0030): qualquer nível/gíria e pedido de sentido."""

from __future__ import annotations

from app.services.prompts import prompt_explain


def test_prompt_explain_nao_recusa_por_nivel_nem_registro() -> None:
    p = prompt_explain("A2-B1", "no cap")

    assert "Nunca** responda ok=false por causa do nível" in p.sistema
    assert "gíria" in p.sistema
    assert "calibra só o vocabulário de apoio" in p.sistema


def test_prompt_explain_aceita_sentido_pedido_depois_do_pipe() -> None:
    p = prompt_explain("B1-B2", "run | to manage a business")

    assert "OU o sentido desejado" in p.sistema
    assert "run | to manage a business" in p.usuario
