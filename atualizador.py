"""
Atualização automática do executável a partir da última Release do GitHub.

Fluxo: consulta a Release mais recente -> se a versão for maior, baixa o .exe e o .sha256 ->
confere a integridade -> troca o executável e reinicia. Nenhum token é usado: o repositório
configurado precisa ter as Releases públicas.
"""

import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from versao import VERSAO

API = "https://api.github.com"
NOME_EXE = "RoboAgregado.exe"
# download só de hosts do próprio GitHub (inclusive após redirecionamentos)
HOSTS_PERMITIDOS = ("api.github.com", "github.com", "objects.githubusercontent.com",
                    "release-assets.githubusercontent.com", "github-releases.githubusercontent.com")
TAMANHO_MIN = 5 * 1024 * 1024      # um executável válido tem vários MB
TAMANHO_MAX = 300 * 1024 * 1024


class ErroAtualizacao(Exception):
    """Falha ao verificar/baixar/aplicar a atualização (mensagem segura para exibir)."""


def versao_tupla(texto: str) -> tuple:
    n = [int(x) for x in re.findall(r"\d+", str(texto))[:3]]
    return tuple(n + [0] * (3 - len(n)))


def _abrir(url: str, timeout: float = 10):
    partes = urlparse(url)
    if partes.scheme != "https" or partes.hostname not in HOSTS_PERMITIDOS:
        raise ErroAtualizacao("Endereço de atualização não permitido.")
    req = urllib.request.Request(url, headers={"User-Agent": "ExtratoFretes-Updater",
                                               "Accept": "application/vnd.github+json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context())
    except urllib.error.HTTPError as e:
        raise ErroAtualizacao(f"HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ssl.SSLError):
        raise ErroAtualizacao("sem conexão com o GitHub") from None
    destino = urlparse(resp.geturl())  # confere também o endereço final, após redirecionamentos
    if destino.scheme != "https" or destino.hostname not in HOSTS_PERMITIDOS:
        resp.close()
        raise ErroAtualizacao("Redirecionamento para endereço não permitido.")
    return resp


def buscar_atualizacao(repositorio: str, versao_atual: str = VERSAO):
    """
    Retorna {'versao', 'url_exe', 'url_sha'} se existir Release mais nova; None se estiver em dia
    (ou se o repositório não tiver Release pública). Levanta ErroAtualizacao em falha de rede.
    """
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repositorio or ""):
        raise ErroAtualizacao("Repositório de atualização inválido no config.ini.")
    try:
        with _abrir(f"{API}/repos/{repositorio}/releases/latest") as resp:
            release = json.load(resp)
    except ErroAtualizacao as e:
        if str(e) == "HTTP 404":   # sem Release publicada (ou repositório privado)
            return None
        raise
    tag = release.get("tag_name", "")
    if release.get("draft") or release.get("prerelease") or not tag:
        return None
    if versao_tupla(tag) <= versao_tupla(versao_atual):
        return None
    ativos = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    if NOME_EXE not in ativos or f"{NOME_EXE}.sha256" not in ativos:
        raise ErroAtualizacao(f"A Release {tag} não contém o executável e o arquivo .sha256.")
    return {"versao": tag.lstrip("vV"), "url_exe": ativos[NOME_EXE],
            "url_sha": ativos[f"{NOME_EXE}.sha256"]}


def baixar_e_verificar(info: dict, destino: Path):
    """Baixa o executável para `destino` e confere o SHA-256. Apaga o arquivo se algo falhar."""
    destino = Path(destino)
    try:
        with _abrir(info["url_sha"]) as resp:
            esperado = re.match(r"\s*([0-9a-fA-F]{64})", resp.read(4096).decode("ascii", "ignore"))
        if not esperado:
            raise ErroAtualizacao("Arquivo .sha256 da Release está em formato inválido.")
        esperado = esperado.group(1).lower()

        sha, total = hashlib.sha256(), 0
        with _abrir(info["url_exe"], timeout=60) as resp, open(destino, "wb") as f:
            while bloco := resp.read(1024 * 1024):
                total += len(bloco)
                if total > TAMANHO_MAX:
                    raise ErroAtualizacao("Arquivo de atualização maior que o esperado.")
                sha.update(bloco)
                f.write(bloco)
        if total < TAMANHO_MIN:
            raise ErroAtualizacao("Arquivo de atualização incompleto.")
        if sha.hexdigest() != esperado:
            raise ErroAtualizacao("A verificação de integridade (SHA-256) falhou; atualização descartada.")
        with open(destino, "rb") as f:
            if f.read(2) != b"MZ":
                raise ErroAtualizacao("O arquivo baixado não é um executável do Windows.")
    except BaseException:
        destino.unlink(missing_ok=True)
        raise


def aplicar_e_reiniciar(novo: Path, atual: Path = None, reiniciar: bool = True):
    """
    Troca o executável em uso pelo novo. O Windows não deixa sobrescrever um .exe em execução,
    mas permite renomeá-lo: o atual vira '.antigo' (apagado na próxima abertura).
    """
    atual = Path(atual or sys.executable)
    novo = Path(novo)
    antigo = atual.with_name(atual.name + ".antigo")
    antigo.unlink(missing_ok=True)
    try:
        os.replace(atual, antigo)
    except OSError:
        raise ErroAtualizacao("Sem permissão para atualizar o programa nesta pasta.") from None
    try:
        os.replace(novo, atual)
    except OSError:
        os.replace(antigo, atual)  # desfaz: nunca deixa o programa sem executável
        raise ErroAtualizacao("Não foi possível instalar a nova versão.") from None
    if reiniciar:
        # o novo processo precisa se comportar como uma abertura normal do executável
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        subprocess.Popen([str(atual)], env=env, cwd=str(atual.parent), close_fds=True,
                         creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP


def limpar_temporarios(atual: Path = None):
    """Remove sobras de atualizações anteriores (.antigo e .novo)."""
    atual = Path(atual or sys.executable)
    for sufixo in (".antigo", ".novo"):
        try:
            atual.with_name(atual.name + sufixo).unlink(missing_ok=True)
        except OSError:
            pass
