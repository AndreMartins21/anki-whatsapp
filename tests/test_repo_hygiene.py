"""Higiene do repositório: garante que a estrutura e as proteções básicas continuam de pé.

Estes testes não dependem de credenciais nem de rede — eles só olham para o próprio repo.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ARQUIVOS_OBRIGATORIOS = [
    ".gitignore",
    ".dockerignore",
    ".env.example",
    ".pre-commit-config.yaml",
    "pyproject.toml",
    "README.md",
    "CLAUDE.md",
]

# Nomes que nunca podem estar versionados.
PADROES_PROIBIDOS = re.compile(
    r"(^\.env$|^\.env\.(?!example)|(^|/)\.env\.infra$|\.pem$|-key\.json$|^service-account)"
)


def _arquivos_versionados() -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files"],  # noqa: S607
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return saida.stdout.splitlines()


def test_arquivos_de_configuracao_existem() -> None:
    faltando = [nome for nome in ARQUIVOS_OBRIGATORIOS if not (RAIZ / nome).exists()]
    assert faltando == [], f"arquivos de configuração ausentes: {faltando}"


def test_nenhum_arquivo_de_segredo_versionado() -> None:
    versionados = [c for c in _arquivos_versionados() if PADROES_PROIBIDOS.search(c)]
    assert versionados == [], f"arquivos de segredo versionados: {versionados}"


def test_env_local_esta_ignorado() -> None:
    resultado = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],  # noqa: S607
        cwd=RAIZ,
    )
    assert resultado.returncode == 0, ".env precisa estar no .gitignore"


def test_env_example_nao_tem_valores_suspeitos() -> None:
    """O .env.example só carrega placeholders — nada que pareça um segredo real."""
    conteudo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    suspeitos = [
        linha
        for linha in conteudo.splitlines()
        if re.search(r"(AIza[0-9A-Za-z_-]{20,}|sk-ant-[0-9A-Za-z_-]{20,}|-----BEGIN)", linha)
    ]
    assert suspeitos == [], f"possível segredo real no .env.example: {suspeitos}"
