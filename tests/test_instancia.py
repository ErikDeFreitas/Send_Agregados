import logging

import pytest
from PySide6.QtWidgets import QWidget
from tcm_ui.modulo import Contexto

from robo_agregado import dados, instancia
from robo_agregado.instancia import RoboAgregado


@pytest.fixture
def inst(qtbot):
    janela = QWidget()
    qtbot.addWidget(janela)
    objeto = RoboAgregado(Contexto("TCMSP\\teste", dados.PASTA, "avulso", logging.getLogger("t"), janela))
    yield objeto
    if objeto.tela is not None:
        qtbot.addWidget(objeto.tela)


def textos(botoes):
    return [b.text().strip() for b in botoes]


def test_widget_e_criado_uma_vez(inst):
    assert inst.widget("extrato") is inst.widget("extrato")


def test_pagina_desconhecida(inst):
    with pytest.raises(KeyError):
        inst.widget("outra")


def test_acoes_microsoft(inst):  # config padrão tem metodo = microsoft
    inst.widget("extrato")
    assert textos(inst.acoes_cabecalho("extrato")) == ["Conta de envio...", "Pasta de dados"]


def test_acoes_outlook(inst, monkeypatch):
    monkeypatch.setattr(inst.widget("extrato"), "metodo", "outlook")
    assert textos(inst.acoes_cabecalho("extrato")) == ["Pasta de dados"]


def test_pode_fechar_durante_envio(inst):
    assert inst.pode_fechar()  # antes de abrir a tela
    inst.widget("extrato").enviando = True
    assert not inst.pode_fechar()


def test_pasta_de_dados_abre_a_pasta(inst, monkeypatch):
    abertos = []
    monkeypatch.setattr(instancia.os, "startfile", abertos.append, raising=False)
    inst.widget("extrato")
    acoes = inst.acoes_cabecalho("extrato")
    acoes[-1].click()
    assert abertos == [dados.PASTA]
