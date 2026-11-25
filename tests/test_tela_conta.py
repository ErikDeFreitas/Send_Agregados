"""Tela do RoboAgregado com a conta Microsoft: diálogo "Conta de envio", primeira abertura e migração do .env."""
import logging

import pytest
from PySide6.QtWidgets import QWidget
from tcm_ui import microsoft
from tcm_ui.components import Modal
from tcm_ui.modulo import Contexto

from robo_agregado import dados, tela
from robo_agregado import enviar_fretes as ef
from robo_agregado.tela import DialogoContaEnvio, TelaExtrato
from tests.conftest import ContaDeTeste


@pytest.fixture
def abertos(monkeypatch):
    """Diálogos "Conta de envio" que a tela abriu (sem bloquear o teste)."""
    lista = []
    monkeypatch.setattr(DialogoContaEnvio, "exec", lambda self: lista.append(self) or 0)
    return lista


def nova_tela(qtbot, fabrica=None, monkeypatch=None):
    if fabrica is not None:
        monkeypatch.setattr(tela, "FABRICA_CONTA", fabrica)
    janela = QWidget()
    qtbot.addWidget(janela)
    t = TelaExtrato(Contexto("TCMSP\teste", dados.PASTA, "avulso", logging.getLogger("t"), janela))
    qtbot.addWidget(t)
    return t


def test_primeira_abertura_sem_login_abre_o_dialogo(qtbot, monkeypatch, abertos):
    t = nova_tela(qtbot, lambda: ContaDeTeste(None), monkeypatch)
    qtbot.waitUntil(lambda: bool(abertos), timeout=3000)
    assert abertos[0].cartao.email() is None
    assert t.conta is not None


def test_logado_nao_abre_o_dialogo(qtbot, abertos):
    t = nova_tela(qtbot)
    qtbot.waitUntil(lambda: t.conta is not None, timeout=3000)
    qtbot.wait(400)
    assert abertos == []


def test_sem_internet_nao_abre_sozinho_e_avisa_no_registro(qtbot, monkeypatch, abertos):
    """Sem internet a tela abre normalmente (nada modal travando a casca ou a verificação do .exe)."""
    def sem_rede():
        raise OSError("sem rede")

    t = nova_tela(qtbot, sem_rede, monkeypatch)
    qtbot.waitUntil(lambda: t._aviso_conta != "", timeout=3000)
    qtbot.wait(300)
    assert abertos == []
    assert microsoft.AVISO_SEM_REDE in t.log.toPlainText()


def test_sem_internet_o_dialogo_mostra_o_motivo(qtbot, monkeypatch, abertos):
    def sem_rede():
        raise OSError("sem rede")

    t = nova_tela(qtbot, sem_rede, monkeypatch)
    qtbot.waitUntil(lambda: t._aviso_conta != "", timeout=3000)
    assert t.pedir_conta() is False
    assert abertos[0].cartao.aviso.text() == microsoft.AVISO_SEM_REDE
    assert not abertos[0].cartao.botao_entrar.isEnabled()


def test_metodo_outlook_nao_cria_conta(qtbot, monkeypatch, abertos):
    def nao_deveria():
        raise AssertionError("não devia criar a conta")

    monkeypatch.setattr(ef, "metodo_envio", lambda cfg: "outlook")
    t = nova_tela(qtbot, nao_deveria, monkeypatch)
    qtbot.wait(300)
    assert t.metodo == "outlook" and t.conta is None and abertos == []


def test_salvar_desligado_sem_login(qtbot):
    d = DialogoContaEnvio(None, ContaDeTeste(None), "")
    qtbot.addWidget(d)
    assert not d.botao_salvar.isEnabled()


def test_enviar_como_invalido_recusa(qtbot):
    d = DialogoContaEnvio(None, ContaDeTeste(), "")
    qtbot.addWidget(d)
    d.campo_enviar_como.setText(" errado ")
    d.botao_salvar.click()
    assert d.resultado is None
    assert d.campo_enviar_como.property("erro") is True


def test_enviar_como_salvo_sem_espacos(qtbot):
    d = DialogoContaEnvio(None, ContaDeTeste(), "")
    qtbot.addWidget(d)
    d.campo_enviar_como.setText("  financeiro@example.com  ")
    d.botao_salvar.click()
    assert d.resultado == "financeiro@example.com"


def test_enviar_como_vazio_usa_a_propria_conta(qtbot):
    d = DialogoContaEnvio(None, ContaDeTeste(), "financeiro@example.com")
    qtbot.addWidget(d)
    assert d.campo_enviar_como.text() == "financeiro@example.com"
    d.campo_enviar_como.setText("")
    d.botao_salvar.click()
    assert d.resultado == ""


def test_pedir_conta_salva_o_enviar_como(qtbot, monkeypatch):
    t = nova_tela(qtbot)
    qtbot.waitUntil(lambda: t.conta is not None, timeout=3000)

    def salvar(self):
        self.campo_enviar_como.setText("financeiro@example.com")
        self.botao_salvar.click()
        return 1

    monkeypatch.setattr(DialogoContaEnvio, "exec", salvar)
    assert t.pedir_conta() is True
    assert ef.ler_prefs()["enviar_como"] == "financeiro@example.com"
    assert t.remetente() == "financeiro@example.com"


def test_remetente_sem_enviar_como_e_a_propria_conta(qtbot):
    t = nova_tela(qtbot)
    qtbot.waitUntil(lambda: t.conta is not None, timeout=3000)
    t.prefs.pop("enviar_como", None)
    assert t.remetente() == "eu@tcm.com"


def test_tela_migra_o_env_ao_abrir(qtbot, monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('SMTP_USUARIO="financeiro@example.com"\nSMTP_SENHA="x"\nEMAIL_CCO="cco@example.com"\n',
                   encoding="utf-8")
    monkeypatch.setattr(ef, "ARQUIVO_ENV", env)
    monkeypatch.setattr(ef, "ARQUIVO_PREFS", tmp_path / "preferencias.json")
    t = nova_tela(qtbot)
    assert not env.exists()
    assert ef.ler_prefs()["enviar_como"] == "financeiro@example.com"
    assert t.campo_cco.text() == "cco@example.com"


def test_sessao_expirada_no_lote_reabre_o_dialogo(qtbot, monkeypatch):
    t = nova_tela(qtbot)
    qtbot.waitUntil(lambda: t.conta is not None, timeout=3000)
    pedidos = []
    monkeypatch.setattr(Modal, "informar", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(t, "pedir_conta", lambda **kw: pedidos.append(kw) or False)
    t.fila.put(("sessao",))
    t.fila.put(("fim", 0, 1, "Sua sessão expirou."))
    t.processar_fila()
    assert pedidos == [{"sessao_expirada": True}]


def test_carregar_planilha_guarda_o_caminho_nas_preferencias(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ef, "ARQUIVO_PREFS", tmp_path / "preferencias.json")
    monkeypatch.setattr(ef, "carregar_dados", lambda cfg, caminho: (None, {}))
    monkeypatch.setattr(ef, "preparar_envios", lambda *a, **k: [])
    t = nova_tela(qtbot)
    t.carregar(str(tmp_path / "planilha.xlsx"))
    assert ef.ler_prefs()["planilha"] == str(tmp_path / "planilha.xlsx")
