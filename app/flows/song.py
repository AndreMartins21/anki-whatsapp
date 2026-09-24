"""Prática com letra de música (M13, seção 5.8, ADR-0016): busca a música, confirma entre
homônimas, recusa letra fora do inglês, pede a explicação de cada verso (feedback + próximo verso
numa mensagem só, como a revisão) e, no fim, oferece salvar o que o aluno não pegou.

As regras sobre a letra (versos, idioma, candidatas) são puras, em `app/domain/musica.py`."""

from __future__ import annotations

import asyncio

from app import messages
from app.domain.choices import eh_todos, parse_numero, parse_numeros
from app.domain.models import (
    Estado,
    ExpressaoDaMusica,
    OpcaoDeMusica,
    Profile,
    Sentence,
    Sessao,
)
from app.domain.musica import (
    Musica,
    eh_ingles,
    escolher_candidatas,
    extrair_versos,
    filtrar_expressoes,
    separar_titulo_e_artista,
)
from app.flows import capture
from app.flows.base import Deps, bloq
from app.services.letras import LetrasIndisponiveis

MAX_EXPRESSOES_OFERECIDAS = 10


async def buscar(d: Deps, sessao: Sessao, texto: str) -> Sessao:
    """`/song <texto>`, ou uma nova busca enquanto o aluno escolhia entre homônimas."""
    if d.letras is None:
        await d.conversa.enviar(messages.SONG_INDISPONIVEL)
        return d.sessao_vazia()
    titulo, artista = separar_titulo_e_artista(texto)
    try:
        async with d.conversa.digitando():
            resultados = await d.letras.buscar(titulo, artista)
            if artista and not resultados:  # o hífen era parte do título: busca livre
                titulo, artista = texto.strip(), None
                resultados = await d.letras.buscar(titulo)
    except LetrasIndisponiveis:
        await d.conversa.enviar(messages.SONG_BUSCA_FALHOU)
        return sessao

    candidatas, fora_do_ingles = escolher_candidatas(resultados, titulo)
    if not candidatas:
        await d.conversa.enviar(messages.song_nao_encontrada(texto.strip(), fora_do_ingles))
        return d.sessao_vazia()
    if len(candidatas) == 1:
        return await _comecar(d, candidatas[0])

    opcoes = [OpcaoDeMusica(id=m.id, titulo=m.titulo, artista=m.artista) for m in candidatas]
    await d.conversa.enviar(messages.song_candidatas(opcoes))
    return d.sessao_vazia().model_copy(
        update={"estado": Estado.SONG_PICKING, "musica_opcoes": opcoes}
    )


async def escolher(d: Deps, sessao: Sessao, texto: str) -> Sessao:
    opcoes = sessao.musica_opcoes
    numero = parse_numero(texto, len(opcoes))
    if numero is None or d.letras is None:
        await d.conversa.enviar(messages.song_candidatas(opcoes, invalida=True))
        return sessao.model_copy(update={"estado": Estado.SONG_PICKING})
    opcao = opcoes[numero - 1]
    try:
        async with d.conversa.digitando():
            musica = await d.letras.obter(opcao.id)
    except LetrasIndisponiveis:
        await d.conversa.enviar(messages.SONG_BUSCA_FALHOU)
        return sessao.model_copy(update={"estado": Estado.SONG_PICKING})
    if musica is None or not musica.letra:
        await d.conversa.enviar(messages.song_nao_encontrada(opcao.titulo, fora_do_ingles=False))
        return d.sessao_vazia()
    return await _comecar(d, musica)


async def cancelar(d: Deps) -> Sessao:
    await d.conversa.enviar(messages.CANCELADO)
    return d.sessao_vazia()


async def _comecar(d: Deps, musica: Musica) -> Sessao:
    letra = musica.letra or ""
    if not eh_ingles(letra):
        await d.conversa.enviar(messages.song_nao_encontrada(musica.titulo, fora_do_ingles=True))
        return d.sessao_vazia()
    versos = extrair_versos(letra)
    if not versos:
        await d.conversa.enviar(messages.SONG_SEM_VERSOS)
        return d.sessao_vazia()
    await d.conversa.enviar(
        messages.song_inicio(musica.titulo, musica.artista, len(versos), versos[0])
    )
    return Sessao(
        estado=Estado.SONG_PRACTICE,
        musica_titulo=musica.titulo,
        musica_artista=musica.artista,
        musica_versos=versos,
        musica_indice=0,
        atualizado_em=d.agora(),
    )


async def responder(d: Deps, sessao: Sessao, perfil: Profile, texto: str) -> Sessao:
    versos = sessao.musica_versos
    indice = sessao.musica_indice
    if indice >= len(versos):  # não deveria acontecer: fecha em vez de travar
        return await _fechar(d, sessao, "", len(versos))

    verso = versos[indice]
    async with d.conversa.digitando():
        linha = await bloq(
            d.tutor.song_line,
            sessao.musica_titulo or "",
            sessao.musica_artista or "",
            verso,
            versos[indice - 1] if indice > 0 else None,
            texto,
            perfil.nivel,
        )

    expressoes = list(sessao.musica_expressoes)
    ja_tem = {e.texto.lower() for e in expressoes}
    for expressao in filtrar_expressoes(linha.expressoes, verso):
        if expressao.lower() not in ja_tem:
            ja_tem.add(expressao.lower())
            expressoes.append(ExpressaoDaMusica(texto=expressao, verso=verso))

    feedback = messages.feedback_de_verso(linha)
    proximo = indice + 1
    atualizada = sessao.model_copy(
        update={
            "estado": Estado.SONG_PRACTICE,
            "musica_indice": proximo,
            "musica_expressoes": expressoes,
        }
    )
    if proximo >= len(versos):
        return await _fechar(d, atualizada, feedback, len(versos))
    await d.conversa.enviar(
        f"{feedback}\n\n{messages.song_verso(proximo + 1, len(versos), versos[proximo])}"
    )
    return atualizada


async def encerrar(d: Deps, sessao: Sessao) -> Sessao:
    """`0` ou `/cancel` no meio da prática: fecha com o resumo do que já foi feito."""
    return await _fechar(d, sessao, "", sessao.musica_indice)


async def _fechar(d: Deps, sessao: Sessao, feedback: str, feitas: int) -> Sessao:
    expressoes = sessao.musica_expressoes[:MAX_EXPRESSOES_OFERECIDAS]
    resumo = messages.song_resumo(
        sessao.musica_titulo or "",
        feitas,
        len(sessao.musica_versos),
        [e.texto for e in expressoes],
    )
    await d.conversa.enviar(f"{feedback}\n\n{resumo}" if feedback else resumo)
    if not expressoes:
        return d.sessao_vazia()
    return d.sessao_vazia().model_copy(
        update={
            "estado": Estado.SONG_SAVING,
            "musica_titulo": sessao.musica_titulo,
            "musica_artista": sessao.musica_artista,
            "musica_expressoes": expressoes,
        }
    )


async def salvar(d: Deps, sessao: Sessao, perfil: Profile, texto: str) -> Sessao:
    """Salva as expressões escolhidas: cada uma é explicada pela IA com o verso como contexto
    (`expressão | verso`, o mesmo formato da captura) e gravada como uma entrada nova."""
    expressoes = sessao.musica_expressoes
    if eh_todos(texto):
        escolhidas = list(expressoes)
    else:
        numeros = parse_numeros(texto, len(expressoes))
        if numeros is None:
            await d.conversa.enviar(messages.song_numeros_invalidos([e.texto for e in expressoes]))
            return sessao.model_copy(update={"estado": Estado.SONG_SAVING})
        escolhidas = [expressoes[n - 1] for n in numeros]

    palavras_do_aluno = [e.palavra for e in await bloq(d.repo.listar_entradas)]
    async with d.conversa.digitando():
        # Explica todas antes de gravar qualquer uma: se a IA falhar, nada fica pela metade e a
        # sessão continua em SONG_SAVING para o aluno tentar de novo.
        explicacoes = await asyncio.gather(
            *(
                bloq(d.tutor.explain, f"{e.texto} | {e.verso}", perfil.nivel, palavras_do_aluno)
                for e in escolhidas
            )
        )

    salvas: list[str] = []
    for explicacao in explicacoes:
        if not explicacao.ok:
            continue
        sentido_id = explicacao.sentido_do_contexto or explicacao.sentidos[0].id
        sentido = next(s for s in explicacao.sentidos if s.id == sentido_id)
        entrada = await bloq(capture.gravar_entrada, d, explicacao, sentido, None)
        await bloq(
            d.repo.adicionar_frase,
            entrada.slug,
            Sentence(texto=sentido.exemplo, autor="bot", criado_em=d.agora()),
        )
        salvas.append(entrada.palavra)
    await d.conversa.enviar(messages.song_salvas(salvas))
    return d.sessao_vazia()


async def descartar(d: Deps) -> Sessao:
    await d.conversa.enviar(messages.SONG_DESCARTADAS)
    return d.sessao_vazia()
