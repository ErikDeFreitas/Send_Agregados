import logging
import threading

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from tcm_ui.modulo import Contexto

from robo_agregado import dados, instancia
from robo_agregado import tela as tela_mod
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


def test_fechar_durante_envio_espera_o_email_atual_ser_registrado(inst, monkeypatch):
    tela = inst.widget("extrato")
    em_envio, soltar, registros = threading.Event(), threading.Event(), []

    class EnviadorLento:
        def __init__(self, *_args):
            pass

        def enviar(self, *_args):
            em_envio.set()
            soltar.wait(5)

        def fechar(self):
            pass

    tela.timer.stop()  # a fila não é lida: os extratos do teste não estão na tabela (e nada de Modal)
    monkeypatch.setattr(tela, "metodo", "microsoft")
    monkeypatch.setattr(tela_mod.ef, "Enviador", EnviadorLento)
    monkeypatch.setattr(tela_mod.ef, "registrar_log", lambda doc, *_a: registros.append(doc))
    envios = [{"doc": d, "nome": "Fulano", "email": "x@exemplo.com", "assunto": d} for d in ("1", "2")]
    tela._thread_envio = threading.Thread(target=tela._enviar_thread, args=(envios, "", "", 0), daemon=True)
    tela._thread_envio.start()
    assert em_envio.wait(5)

    threading.Timer(0.3, soltar.set).start()
    QApplication.instance().aboutToQuit.emit()  # encerrar_envio: só volta com a thread terminada
    assert not tela._thread_envio.is_alive()
    assert registros == ["1"]  # o e-mail em curso foi registrado; o segundo não foi enviado


def test_encerrar_envio_tem_limite(inst):
    tela = inst.widget("extrato")
    soltar = threading.Event()
    tela._thread_envio = threading.Thread(target=soltar.wait, args=(5,), daemon=True)
    tela._thread_envio.start()
    tela.encerrar_envio(0.1)
    assert tela.parar.is_set() and tela._thread_envio.is_alive()
    soltar.set()


def test_pasta_de_dados_abre_a_pasta(inst, monkeypatch):
    abertos = []
    monkeypatch.setattr(instancia.os, "startfile", abertos.append, raising=False)
    inst.widget("extrato")
    acoes = inst.acoes_cabecalho("extrato")
    acoes[-1].click()
    assert abertos == [dados.PASTA]
