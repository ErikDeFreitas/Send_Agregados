import os
import tempfile

# Antes de qualquer import do pacote: nenhum teste pode tocar a pasta real %LOCALAPPDATA%\RoboAgregado.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ROBO_AGREGADO_DADOS"] = tempfile.mkdtemp(prefix="robo_agregado_dados_")
os.environ["TCM_CONTA_MICROSOFT"] = tempfile.mkdtemp(prefix="conta_microsoft_")

import pytest  # noqa: E402
from PySide6 import QtCore  # noqa: E402


class _QSettingsIni(QtCore.QSettings):
    """QSettings(org, app) em arquivo .ini (pasta temporária), nunca no registro do Windows.

    No Qt 6, QSettings(org, app) ignora setDefaultFormat() e usa sempre o registro; por isso a classe é
    trocada em PySide6.QtCore antes de qualquer `from PySide6.QtCore import QSettings`.
    """

    def __init__(self, *args, **kwargs):
        if 1 <= len(args) <= 2 and not kwargs and all(isinstance(a, str) for a in args):
            super().__init__(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, *args)
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _QSettingsIni
from PySide6.QtCore import QSettings  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _qsettings_fora_do_registro(tmp_path_factory):
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("qsettings")))


class ContaDeTeste:
    """Conta Microsoft falsa: nenhum teste fala com a Microsoft."""

    def __init__(self, email="eu@tcm.com"):
        self._email = email
        self.saiu = False

    def email(self):
        return self._email

    def entrar(self):
        self._email = "eu@tcm.com"
        return self._email

    def token(self):
        return "T"

    def sair(self):
        self._email = None
        self.saiu = True


@pytest.fixture(autouse=True)
def _conta_falsa(monkeypatch):
    from robo_agregado import tela
    monkeypatch.setattr(tela, "FABRICA_CONTA", lambda: ContaDeTeste("eu@tcm.com"))
