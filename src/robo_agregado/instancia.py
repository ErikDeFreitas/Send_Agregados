"""Instância do RoboAgregado aberta na casca ou no avulso (páginas e ações do cabeçalho)."""

import os

from PySide6.QtWidgets import QWidget
from tcm_ui.components import Botao
from tcm_ui.modulo import Contexto

from robo_agregado import dados
from robo_agregado.tela import TelaExtrato


class RoboAgregado:
    def __init__(self, contexto: Contexto):
        self.contexto = contexto
        self.tela: TelaExtrato | None = None

    def widget(self, chave_pagina: str) -> QWidget:
        if chave_pagina != "extrato":
            raise KeyError(chave_pagina)
        if self.tela is None:
            self.tela = TelaExtrato(self.contexto)
        return self.tela

    def acoes_cabecalho(self, chave_pagina: str) -> list[QWidget]:
        acoes = []
        if self.tela is not None and self.tela.metodo == "smtp":
            credenciais = Botao("Credenciais...", "secundario", icone="chave")
            credenciais.clicked.connect(self.tela.pedir_credenciais)
            acoes.append(credenciais)
        pasta = Botao("Pasta de dados", "secundario", icone="pasta")
        pasta.clicked.connect(self._abrir_pasta)
        acoes.append(pasta)
        return acoes

    def pode_fechar(self) -> bool:
        return self.tela is None or not self.tela.enviando  # nunca fecha no meio de um envio

    @staticmethod
    def _abrir_pasta():
        dados.preparar_pasta()
        os.startfile(dados.PASTA)
