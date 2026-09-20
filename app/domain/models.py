"""Modelos de domínio (seções 6 e 7.1 da spec): o que entra no banco ou na sessão, e os
schemas de saída do LLM (`Explanation`, `Evaluation`, `Exemplos`, `Expansoes`)."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NivelUsuario = Literal["A2-B1", "B1-B2", "B2-C1"]
ModoPratica = Literal["guiado", "producao_primeiro"]
Cefr = Literal["A2", "B1", "B2", "C1", "C2"]
Tag = Literal["trabalho", "phrasal_verb", "expressao"]
Veredito = Literal["correta", "correta_pouco_natural", "quase", "incorreta"]
StatusEntrada = Literal["nova", "praticada"]
TipoExpansao = Literal["colocacao", "familia", "phrasal_verb", "sinonimo", "expressao"]


def agora_utc() -> datetime:
    return datetime.now(UTC)


class Estado(StrEnum):
    """Estados da conversa (seção 5.1). `AWAIT_NEW_WORD` e `AWAIT_EXPANSION_PRACTICE` são as
    duas perguntas de 1/2 que a spec descreve no texto mas não nomeia no diagrama."""

    IDLE = "IDLE"
    AWAIT_SENSE = "AWAIT_SENSE"
    AWAIT_CHOICE = "AWAIT_CHOICE"
    AWAIT_SENTENCE = "AWAIT_SENTENCE"
    AWAIT_NEXT = "AWAIT_NEXT"
    AWAIT_AFTER_EXAMPLES = "AWAIT_AFTER_EXAMPLES"
    AWAIT_NEW_WORD = "AWAIT_NEW_WORD"
    OFFER_EXPANSION = "OFFER_EXPANSION"
    AWAIT_EXPANSION_PRACTICE = "AWAIT_EXPANSION_PRACTICE"


class Sense(BaseModel):
    id: str
    traducao: str
    definicao: str
    exemplo_curto: str


class Expansion(BaseModel):
    expressao: str
    traducao: str
    tipo: TipoExpansao


class Explanation(BaseModel):
    """Saída de `explain` (seção 6). Com `ok=False` só `motivo_erro` importa, então os demais
    campos têm padrão — o modelo não precisa inventar conteúdo para uma entrada inválida."""

    ok: bool
    motivo_erro: str | None = None
    palavra: str = ""  # forma base, minúsculas
    classe: str = ""  # PT-BR
    cefr_estimado: Cefr = "B1"
    sentidos: list[Sense] = Field(default_factory=list, max_length=4)  # só os comuns
    sentido_do_contexto: str | None = None  # id do sentido, se o contexto (ou a unicidade) o define
    frase_contexto: str | None = None  # frase do usuário corrigida, alvo entre [[ ]]
    nota: str = ""
    tags: list[Tag] = Field(default_factory=list)

    @model_validator(mode="after")
    def _explicacao_valida_tem_palavra_e_sentidos(self) -> Explanation:
        if self.ok and not (self.palavra.strip() and self.sentidos):
            raise ValueError("ok=true exige `palavra` e ao menos 1 sentido")
        ids = {sentido.id for sentido in self.sentidos}
        if self.sentido_do_contexto is not None and self.sentido_do_contexto not in ids:
            raise ValueError("`sentido_do_contexto` deve ser o id de um dos `sentidos`")
        return self


MAX_LINHAS_EXPLICACAO = 4


class Evaluation(BaseModel):
    """Saída de `evaluate` (seção 6)."""

    usa_palavra_alvo: bool  # considera flexões
    sentido_correto: bool
    veredito: Veredito
    correcoes: list[str]  # "errado → certo"
    versao_natural: str  # alvo entre [[ ]]
    explicacao: str  # PT-BR, máx. 4 linhas

    @model_validator(mode="after")
    def _explicacao_curta(self) -> Evaluation:
        if len(self.explicacao.strip().splitlines()) > MAX_LINHAS_EXPLICACAO:
            raise ValueError(f"`explicacao` deve ter no máximo {MAX_LINHAS_EXPLICACAO} linhas")
        return self


class Exemplos(BaseModel):
    """Saída de `examples`: frases com o alvo entre [[ ]]."""

    frases: list[str]

    @model_validator(mode="after")
    def _alvo_marcado(self) -> Exemplos:
        if not all("[[" in frase and "]]" in frase for frase in self.frases):
            raise ValueError("toda frase deve marcar a palavra-alvo entre [[ ]]")
        return self


class Expansoes(BaseModel):
    """Saída de `expansions`: de 3 a 5 expressões relacionadas."""

    itens: list[Expansion] = Field(min_length=3, max_length=5)


class SentidoSalvo(BaseModel):
    traducao: str
    definicao: str


class Sentence(BaseModel):
    """Documento de `entries/{slug}/sentences/{auto}`."""

    texto: str
    autor: Literal["usuario", "bot"]
    veredito: Veredito | None = None
    correcoes: list[str] | None = None
    versao_natural: str | None = None
    explicacao: str | None = None
    criado_em: datetime = Field(default_factory=agora_utc)


class Entry(BaseModel):
    """Documento de `entries/{slug}`. O `slug` é o id do documento."""

    model_config = ConfigDict(use_enum_values=True)

    slug: str
    palavra: str
    classe: str
    cefr_estimado: Cefr
    sentido: SentidoSalvo
    outros_sentidos: list[SentidoSalvo] = Field(default_factory=list)
    nota: str = ""
    tags: list[Tag] = Field(default_factory=list)
    origem_texto: str | None = None
    origem: Literal["usuario", "expansao"] = "usuario"
    pai: str | None = None
    status: StatusEntrada = "nova"
    exportado: bool = False
    criado_em: datetime = Field(default_factory=agora_utc)
    atualizado_em: datetime = Field(default_factory=agora_utc)


class Profile(BaseModel):
    """Documento `profile/me`."""

    nivel: NivelUsuario
    modo: ModoPratica
    criado_em: datetime = Field(default_factory=agora_utc)


class Sessao(BaseModel):
    """Documento `session/current`.

    Além dos campos da spec, guarda o que o usuário está escolhendo em menus numerados: a
    explicação inteira enquanto ele escolhe o sentido (`explicacao_pendente`), as expansões
    sugeridas (`expansoes_sugeridas`) e as entradas criadas a partir delas (`expansoes_criadas`).
    Sem isso, "1,3" numa mensagem não teria como apontar para nada na mensagem seguinte.
    """

    model_config = ConfigDict(use_enum_values=True)

    estado: Estado = Estado.IDLE
    entry_id: str | None = None
    sentido_id: str | None = None
    pendente_nova_palavra: str | None = None
    explicacao_pendente: Explanation | None = None
    expansoes_sugeridas: list[Expansion] = Field(default_factory=list)
    expansoes_criadas: list[str] = Field(default_factory=list)
    atualizado_em: datetime = Field(default_factory=agora_utc)


def slugify(palavra: str) -> str:
    """minúsculas, `[^a-z0-9]+` -> `-` (seção 7.1); acentos são descartados antes."""
    sem_acento = unicodedata.normalize("NFKD", palavra).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
