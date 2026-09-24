"""M15 (ADR-0018) no webhook: quem não tem plano só recebe o aviso (e a IA nunca é chamada), grupo
só é ativado por admin, e o grupo não ativado fica pendente em silêncio."""

from __future__ import annotations

import logging

import pytest

from app import messages
from tests.helpers import T0
from tests.webhook_helpers import (
    ADMIN,
    ALUNO_COMUM,
    DONO,
    ESTRANHO,
    GRUPO,
    GRUPO_FIXO,
    Ambiente,
    _do_grupo,
    _entrada_no_grupo,
    _privada,
)

# --- privado: número sem plano ---------------------------------------------------------------


def test_estranho_recebe_o_aviso_e_a_ia_nunca_e_chamada(ambiente: Ambiente) -> None:
    resposta = ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "stall"))

    assert resposta.status_code == 200
    assert ambiente.canal.textos_enviados == [
        (f"{ESTRANHO}@c.us", messages.sem_plano(ambiente.settings.contact_email))
    ]
    assert ambiente.tutor.chamadas == []
    assert ambiente.canal.vistos == []  # sem sendSeen
    assert ambiente.banco.do_espaco(f"{ESTRANHO}@c.us").obter_perfil() is None  # nada gravado


def test_o_aviso_mostra_o_email_e_a_linha_em_portugues(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "oi"))

    (_, texto) = ambiente.canal.textos_enviados[0]
    assert "smartins.bot@gmail.com" in texto
    assert "🇧🇷 Você não possui um plano com o nosso bot" in texto


def test_o_aviso_vai_no_maximo_uma_vez_e_o_resto_e_silencio(ambiente: Ambiente) -> None:
    for texto in ("oi", "stall", "/list", "/admin add 5541966665555"):
        ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, texto))

    assert len(ambiente.canal.textos_enviados) == 1
    assert ambiente.tutor.chamadas == []
    assert ambiente.banco.listar_admins() == [ADMIN]  # o comando dele não fez nada


def test_cada_estranho_recebe_o_proprio_aviso(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "oi"))
    ambiente.cliente.post("/waha/webhook", json=_privada("5541955554444", "oi"))

    assert [c for c, _ in ambiente.canal.textos_enviados] == [
        f"{ESTRANHO}@c.us",
        "5541955554444@c.us",
    ]


def test_midia_de_estranho_tambem_so_recebe_o_aviso(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "", midia=True))

    assert [t for _, t in ambiente.canal.textos_enviados] == [
        messages.sem_plano(ambiente.settings.contact_email)
    ]


def test_mensagem_vazia_de_estranho_e_ignorada_sem_gastar_o_aviso(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "   "))
    assert ambiente.canal.textos_enviados == []

    ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "oi"))
    assert len(ambiente.canal.textos_enviados) == 1


def test_a_marca_do_aviso_nao_guarda_o_telefone_em_claro(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ESTRANHO, "oi"))

    marcas = [m for m in ambiente.banco._processadas if m.startswith("aviso_")]
    assert len(marcas) == 1
    assert ESTRANHO not in marcas[0]


def test_aluno_e_dono_continuam_sendo_atendidos_normalmente(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ALUNO_COMUM, "stall"))
    ambiente.cliente.post("/waha/webhook", json=_privada(DONO, "stall"))

    assert [c for c, _ in ambiente.canal.textos_enviados] == [
        f"{ALUNO_COMUM}@c.us",
        f"{DONO}@c.us",
    ]
    assert len(ambiente.tutor.chamadas) == 2


# --- privado: admin e dono -------------------------------------------------------------------


def test_admin_que_nao_e_aluno_usa_groups_sem_chamar_a_ia(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ADMIN, "/groups"))

    ((chat, texto),) = ambiente.canal.textos_enviados
    assert chat == f"{ADMIN}@c.us"
    assert "Active groups" in texto
    assert ambiente.tutor.chamadas == []


def test_admin_que_nao_e_aluno_recebe_o_aviso_para_qualquer_outra_coisa(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ADMIN, "stall"))
    ambiente.cliente.post("/waha/webhook", json=_privada(ADMIN, "/admin add 5541966665555"))

    assert [t for _, t in ambiente.canal.textos_enviados] == [
        messages.sem_plano(ambiente.settings.contact_email)
    ]
    assert ambiente.tutor.chamadas == []
    assert ambiente.banco.listar_admins() == [ADMIN]


def test_dono_gerencia_admins_pelo_privado(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(DONO, f"/admin add {ESTRANHO}"))

    assert ambiente.canal.textos_enviados == [(f"{DONO}@c.us", messages.ADMIN_ADICIONADO)]
    assert ESTRANHO in ambiente.banco.listar_admins()
    assert ambiente.tutor.chamadas == []


def test_aluno_comum_que_manda_admin_ou_groups_recebe_comando_desconhecido(
    ambiente: Ambiente,
) -> None:
    ambiente.cliente.post("/waha/webhook", json=_privada(ALUNO_COMUM, "/admin add 5541966665555"))
    ambiente.cliente.post("/waha/webhook", json=_privada(ALUNO_COMUM, "/groups"))

    assert [t for _, t in ambiente.canal.textos_enviados] == [messages.COMANDO_DESCONHECIDO] * 2
    assert ambiente.banco.listar_admins() == [ADMIN]


# --- grupo: ativar ---------------------------------------------------------------------------


def test_admin_ativa_o_grupo_com_activate(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{ADMIN}@c.us", "!activate"))

    assert ambiente.canal.textos_enviados == [(GRUPO, messages.GRUPO_ATIVADO)]
    assert ambiente.banco.grupo_esta_ativo(GRUPO)
    assert ambiente.banco.listar_grupos_pendentes() == []
    assert ambiente.tutor.chamadas == []


def test_activate_de_quem_nao_e_admin_e_silencio_total_mas_o_grupo_fica_pendente(
    ambiente: Ambiente,
) -> None:
    ambiente.cliente.post(
        "/waha/webhook", json=_do_grupo(GRUPO, f"{ALUNO_COMUM}@c.us", "!activate")
    )

    assert ambiente.canal.textos_enviados == []
    assert ambiente.canal.vistos == []
    assert not ambiente.banco.grupo_esta_ativo(GRUPO)
    assert [g for g, _ in ambiente.banco.listar_grupos_pendentes()] == [GRUPO]


def test_o_dono_tambem_ativa(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{DONO}@c.us", "!activate"))

    assert ambiente.banco.grupo_esta_ativo(GRUPO)


def test_admin_que_aparece_como_lid_e_resolvido_pelo_cache_de_lids(ambiente: Ambiente) -> None:
    ambiente.canal.lids_conhecidos["777@lid"] = ADMIN

    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, "777@lid", "!activate"))

    assert ambiente.banco.grupo_esta_ativo(GRUPO)
    assert ambiente.banco.obter_numero_do_lid("777@lid") == ADMIN


def test_activate_com_lid_nao_resolvido_ou_sem_participante_e_ignorado(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, "999@lid", "!activate"))
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, None, "!activate"))

    assert ambiente.canal.textos_enviados == []
    assert not ambiente.banco.grupo_esta_ativo(GRUPO)


def test_activate_no_meio_da_conversa_nao_conta(ambiente: Ambiente) -> None:
    ambiente.cliente.post(
        "/waha/webhook", json=_do_grupo(GRUPO, f"{ADMIN}@c.us", "gente, !activate o bot")
    )

    assert not ambiente.banco.grupo_esta_ativo(GRUPO)


def test_o_mesmo_activate_reenviado_pelo_waha_e_tratado_uma_vez(ambiente: Ambiente) -> None:
    corpo = _do_grupo(GRUPO, f"{ADMIN}@c.us", "!activate", id_="false_grupo_ID_FIXO")

    ambiente.cliente.post("/waha/webhook", json=corpo)
    ambiente.cliente.post("/waha/webhook", json=corpo)

    assert len(ambiente.canal.textos_enviados) == 1


def test_o_limite_de_grupos_recusa_e_avisa_no_grupo(ambiente: Ambiente) -> None:
    ambiente.settings.max_groups = 1
    ambiente.cliente.post("/waha/webhook", json=_do_grupo("1@g.us", f"{ADMIN}@c.us", "!activate"))

    ambiente.cliente.post("/waha/webhook", json=_do_grupo("2@g.us", f"{ADMIN}@c.us", "!activate"))

    assert ambiente.canal.textos_enviados[-1] == ("2@g.us", messages.grupo_limite(1))
    assert not ambiente.banco.grupo_esta_ativo("2@g.us")


def test_deactivate_desliga_e_o_bot_volta_ao_silencio(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{ADMIN}@c.us", "!activate"))
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{ADMIN}@c.us", "!deactivate"))

    assert [t for _, t in ambiente.canal.textos_enviados] == [
        messages.GRUPO_ATIVADO,
        messages.GRUPO_DESATIVADO,
    ]
    assert not ambiente.banco.grupo_esta_ativo(GRUPO)


# --- grupo: pendente e silêncio --------------------------------------------------------------


def test_conversa_em_grupo_nao_ativado_nao_e_lida_e_o_grupo_vira_pendente(
    ambiente: Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        ambiente.cliente.post(
            "/waha/webhook",
            json=_do_grupo(GRUPO, f"{ALUNO_COMUM}@c.us", "conversa secreta da turma"),
        )

    assert ambiente.canal.textos_enviados == [] and ambiente.canal.vistos == []
    assert ambiente.tutor.chamadas == []
    assert [g for g, _ in ambiente.banco.listar_grupos_pendentes()] == [GRUPO]
    assert not any("conversa secreta" in r.message for r in caplog.records)  # nunca o conteúdo
    assert ambiente.banco._processadas == set()  # nem a deduplicação grava nada


def test_grupo_pendente_e_registrado_uma_vez_com_o_primeiro_horario(ambiente: Ambiente) -> None:
    for _ in range(3):
        ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{ALUNO_COMUM}@c.us", "oi"))

    assert len(ambiente.banco.listar_grupos_pendentes()) == 1


def test_grupo_fixo_do_env_e_grupo_ativo_nao_viram_pendentes(ambiente: Ambiente) -> None:
    ambiente.banco.ativar_grupo(GRUPO, nome=None, por=ADMIN, agora=T0)

    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO_FIXO, f"{ALUNO_COMUM}@c.us", "oi"))
    ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{ALUNO_COMUM}@c.us", "oi"))

    assert ambiente.banco.listar_grupos_pendentes() == []
    assert ambiente.canal.textos_enviados == []


def test_o_bot_ser_adicionado_a_um_grupo_o_deixa_pendente(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_entrada_no_grupo(GRUPO))

    assert [g for g, _ in ambiente.banco.listar_grupos_pendentes()] == [GRUPO]
    assert ambiente.canal.textos_enviados == []  # silêncio: nem um "oi"


def test_entrada_em_grupo_ja_autorizado_nao_gera_pendente(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_entrada_no_grupo(GRUPO_FIXO))

    assert ambiente.banco.listar_grupos_pendentes() == []


def test_o_id_do_grupo_novo_aparece_no_log_uma_vez(
    ambiente: Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        ambiente.cliente.post("/waha/webhook", json=_entrada_no_grupo(GRUPO))
        ambiente.cliente.post("/waha/webhook", json=_do_grupo(GRUPO, f"{ALUNO_COMUM}@c.us", "oi"))

    assert len([r for r in caplog.records if GRUPO in r.message]) == 1
