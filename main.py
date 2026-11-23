"""Ponto de entrada do RoboAgregado avulso (.exe ou `python main.py`)."""

import sys

from robo_agregado import dados
from robo_agregado.modulo import MODULO
from tcm_ui.avulso import rodar_avulso

if __name__ == "__main__":
    sys.exit(rodar_avulso(MODULO, atualizar=dados.atualizacao_ativa()))
