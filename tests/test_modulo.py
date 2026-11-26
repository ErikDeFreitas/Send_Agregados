import os
import subprocess
import sys
from importlib.metadata import entry_points

from PySide6.QtCore import QSettings
from tcm_ui.components import CartaoErro
from tcm_ui.janela import JanelaPrincipal

import robo_agregado
from robo_agregado.modulo import MODULO
from robo_agregado.tela import TelaExtrato


def test_entry_point_expoe_modulo():
    eps = {ep.name: ep for ep in entry_points(group="sistema_financeiro.modulos")}
    modulo = eps["robo_agregado"].load()
    assert (modulo.id, modulo.grupo_ad, modulo.nome_exe) == ("robo_agregado", "SF-RoboAgregado", "RoboAgregado.exe")
    assert modulo.versao == robo_agregado.__version__ == "2.1.1"
    assert [p.chave for p in modulo.paginas] == ["extrato"]
    assert modulo.aplicacao_settings == "RoboAgregado"


def test_modulo_e_leve(tmp_path):
    codigo = ("import sys, robo_agregado.modulo; "
              "print('pandas' in sys.modules, 'robo_agregado.tela' in sys.modules)")
    env = {**os.environ, "ROBO_AGREGADO_DADOS": str(tmp_path / "nao_criar")}
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, check=True)
    assert saida.stdout.split() == ["False", "False"]
    assert not (tmp_path / "nao_criar").exists()


def test_abre_na_janela_da_casca(qtbot):
    jan = JanelaPrincipal([MODULO], nome_app="Teste", icone_app="painel", usuario="TCMSP\\teste",
                          modo="casca", configuracoes=QSettings("TCM-teste", "Robo"))
    qtbot.addWidget(jan)
    assert jan.pagina_atual == ("robo_agregado", "extrato")
    assert jan.findChildren(TelaExtrato) and not jan.findChildren(CartaoErro)
