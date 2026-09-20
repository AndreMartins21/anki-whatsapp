"""Higiene dos ADRs: numeração, cabeçalho, status, seções e índice.

Estes testes não dependem de credenciais nem de rede — eles só leem `docs/adr/`.
O processo completo está em `docs/adr/README.md` e na skill `adr`.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_ADR = RAIZ / "docs" / "adr"
TEMPLATE = DIR_ADR / "0000-template.md"
INDICE = DIR_ADR / "README.md"

NOME_ADR = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
TITULO_ADR = re.compile(r"^# ADR-(\d{4}): .+$")
STATUS_ADR = re.compile(
    r"^- \*\*Status:\*\* (Proposto|Aceito|Substituído por ADR-\d{4}|Descartado)$"
)
DATA_ADR = re.compile(r"^- \*\*Data:\*\* \d{4}-\d{2}-\d{2}$")

SECOES_OBRIGATORIAS = [
    "## Contexto",
    "## Decisão",
    "## Alternativas consideradas",
    "## Consequências",
]


def _adrs() -> list[Path]:
    """Todos os ADRs de verdade, em ordem — o template (0000) não conta como decisão."""
    return sorted(p for p in DIR_ADR.glob("*.md") if NOME_ADR.match(p.name) and p != TEMPLATE)


def test_diretorio_de_adr_existe_com_template_e_indice() -> None:
    assert DIR_ADR.is_dir(), "docs/adr/ precisa existir"
    assert TEMPLATE.exists(), "docs/adr/0000-template.md precisa existir"
    assert INDICE.exists(), "docs/adr/README.md precisa existir"


def test_nomes_de_arquivo_seguem_o_padrao() -> None:
    fora_do_padrao = [
        p.name for p in DIR_ADR.glob("*.md") if p.name != "README.md" and not NOME_ADR.match(p.name)
    ]
    assert fora_do_padrao == [], f"esperado NNNN-titulo-curto.md: {fora_do_padrao}"


def test_numeracao_e_sequencial_sem_buraco_nem_repeticao() -> None:
    numeros = [int(NOME_ADR.match(p.name).group(1)) for p in _adrs()]  # type: ignore[union-attr]
    esperado = list(range(1, len(numeros) + 1))
    assert numeros == esperado, f"numeração deveria ser {esperado}, é {numeros}"


def test_titulo_bate_com_o_numero_do_arquivo() -> None:
    for adr in _adrs():
        numero = NOME_ADR.match(adr.name).group(1)  # type: ignore[union-attr]
        primeira_linha = adr.read_text(encoding="utf-8").splitlines()[0]
        casamento = TITULO_ADR.match(primeira_linha)
        assert casamento, f"{adr.name}: primeira linha deveria ser '# ADR-{numero}: <título>'"
        assert casamento.group(1) == numero, (
            f"{adr.name}: título diz ADR-{casamento.group(1)}, arquivo diz {numero}"
        )


def test_status_e_data_sao_validos() -> None:
    for adr in _adrs():
        linhas = adr.read_text(encoding="utf-8").splitlines()
        assert any(STATUS_ADR.match(linha) for linha in linhas), (
            f"{adr.name}: falta '- **Status:** Proposto|Aceito|Substituído por ADR-NNNN|Descartado'"
        )
        assert any(DATA_ADR.match(linha) for linha in linhas), (
            f"{adr.name}: falta '- **Data:** AAAA-MM-DD'"
        )


def test_secoes_obrigatorias_estao_presentes() -> None:
    for adr in _adrs():
        conteudo = adr.read_text(encoding="utf-8")
        faltando = [secao for secao in SECOES_OBRIGATORIAS if secao not in conteudo]
        assert faltando == [], f"{adr.name}: seções ausentes: {faltando}"


def test_adr_substituido_aponta_para_um_adr_existente() -> None:
    numeros = {NOME_ADR.match(p.name).group(1) for p in _adrs()}  # type: ignore[union-attr]
    for adr in _adrs():
        for alvo in re.findall(r"Substituído por ADR-(\d{4})", adr.read_text(encoding="utf-8")):
            assert alvo in numeros, f"{adr.name} aponta para ADR-{alvo}, que não existe"


def test_indice_lista_todos_os_adrs() -> None:
    indice = INDICE.read_text(encoding="utf-8")
    ausentes = [adr.name for adr in _adrs() if f"]({adr.name})" not in indice]
    assert ausentes == [], f"ADRs fora do índice de docs/adr/README.md: {ausentes}"
