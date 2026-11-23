"""Pasta de dados e config.ini embutido do RoboAgregado. Só stdlib; nada é criado ao importar."""

import configparser
import logging
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from robo_agregado import __version__

NOME_PASTA = "RoboAgregado"
CONFIG_EMBUTIDO = resources.files("robo_agregado") / "config.ini"
_ARQUIVOS_ANTIGOS = (".env", "log_envios.csv", "preferencias.json")


def pasta_dados() -> Path:
    var = os.environ.get("ROBO_AGREGADO_DADOS")
    if var:
        return Path(var)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / NOME_PASTA


PASTA: Path = pasta_dados()


def preparar_pasta() -> Path:
    """Cria a pasta de dados; no RoboAgregado.exe avulso, traz os arquivos que ficavam ao lado do .exe."""
    PASTA.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False) and Path(sys.executable).name.lower() == "roboagregado.exe":
        for nome in _ARQUIVOS_ANTIGOS:
            antigo = Path(sys.executable).resolve().parent / nome
            if antigo.is_file() and not (PASTA / nome).exists():
                try:
                    shutil.move(str(antigo), str(PASTA / nome))
                except OSError:
                    pass
    return PASTA


def _versao_tupla(texto: str):
    """'2.10.0' -> (2, 10, 0); None quando não for numérica (X.Y.Z)."""
    try:
        return tuple(int(parte) for parte in texto.strip().split("."))
    except ValueError:
        return None


def atualizar_config_embutido(caminho: Path, versao: str) -> None:
    """Cria o config.ini na 1ª execução e o substitui pelo embutido só quando a versão embutida é MAIOR
    que a da marca config.versao (o anterior fica em config.ini.bak). Versão igual ou menor não toca em
    nada, para que alternar entre versões não apague as edições do usuário."""
    marca = caminho.with_name("config.versao")
    try:
        versao_local = marca.read_text(encoding="utf-8").strip()
    except OSError:
        versao_local = ""
    if caminho.exists():
        local, embutida = _versao_tupla(versao_local), _versao_tupla(versao)
        if local is not None and (embutida is None or embutida <= local):
            return
    try:
        if caminho.exists():
            shutil.copy2(caminho, caminho.with_name("config.ini.bak"))
        caminho.write_bytes(CONFIG_EMBUTIDO.read_bytes())
        marca.write_text(versao, encoding="utf-8")
    except OSError:
        pass  # sem permissão: segue com o config.ini que já existe


def garantir_config() -> Path:
    preparar_pasta()
    caminho = PASTA / "config.ini"
    atualizar_config_embutido(caminho, __version__)
    return caminho


def atualizacao_ativa() -> bool:
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read(garantir_config(), encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        logging.getLogger("robo_agregado").warning(
            "config.ini ilegível; seguindo com a atualização automática ligada.", exc_info=True)
        return True
    valor = cfg.get("atualizacao", "ativo", fallback="sim")
    return valor.strip().lower() in ("sim", "s", "true", "1")
