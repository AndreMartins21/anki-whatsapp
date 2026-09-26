"""FakeSintetizador (M23): dublê em memória do TTS, para testes — nunca faz chamada de rede."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeSintetizador:
    chamadas: list[tuple[str, str]] = field(default_factory=list)
    falha: bool = False

    def sintetizar(self, texto: str, voz: str) -> bytes:
        self.chamadas.append((texto, voz))
        if self.falha:
            raise RuntimeError("falha simulada do TTS")
        return f"ogg:{texto}".encode()
