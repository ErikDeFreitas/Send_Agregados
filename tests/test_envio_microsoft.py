"""Envio com a conta Microsoft da própria pessoa, "Enviar como" a caixa responsável (sem senha)."""
import configparser
import smtplib

import pytest
from tcm_ui import microsoft
from tcm_ui.microsoft import FalhaLogin

from robo_agregado import enviar_fretes as ef


def cfg(metodo="microsoft"):
    c = configparser.ConfigParser(interpolation=None)
    c.read_string(f"[email]\nmetodo = {metodo}\n[smtp]\nnome_remetente =\n")
    return c


def envio(email="a@example.com"):
    return {"doc": "12345678000190", "nome": "Agregado", "email": email,
            "assunto": "Extrato de Fretes - Agregado - Semana 42", "corpo": "<p>Olá</p>"}


class ContaFalsa:
    def __init__(self, email="eu@tcm.com", token="T", falha=None):
        self._email, self._token, self.falha = email, token, falha

    def email(self):
        return self._email

    def token(self):
        if self.falha:
            raise self.falha
        return self._token


class SMTPFalso:
    def __init__(self, erro=None):
        self.erro = erro
        self.login = self.from_addr = self.to_addrs = self.msg = None

    def send_message(self, msg, from_addr, to_addrs):
        if self.erro:
            raise self.erro
        self.msg, self.from_addr, self.to_addrs = msg, from_addr, to_addrs

    def quit(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    servidor = SMTPFalso()

    def abrir(email, token):
        servidor.login = (email, token)
        return servidor

    monkeypatch.setattr(microsoft, "abrir_smtp", abrir)
    return servidor


# --- método -----------------------------------------------------------------

def test_metodo_smtp_antigo_vira_microsoft():
    assert ef.metodo_envio(cfg("smtp")) == "microsoft"


def test_metodo_microsoft():
    assert ef.metodo_envio(cfg("microsoft")) == "microsoft"


def test_metodo_outlook_continua():
    assert ef.metodo_envio(cfg(" Outlook ")) == "outlook"


def test_config_embutido_usa_microsoft():
    from robo_agregado import dados
    embutido = configparser.ConfigParser(interpolation=None)
    embutido.read_string(dados.CONFIG_EMBUTIDO.read_text(encoding="utf-8"))
    assert embutido["email"]["metodo"] == "microsoft"
    assert "servidor" not in embutido["smtp"] and "porta" not in embutido["smtp"]


# --- migração do .env ---------------------------------------------------------

def test_migrar_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text('﻿SMTP_USUARIO="financeiro@example.com"\nSMTP_SENHA="x"\n\n'
                   "EMAIL_CCO='cco@example.com'\n", encoding="utf-8")
    prefs = {}
    assert ef.migrar_env(prefs, env) is True
    assert prefs == {"enviar_como": "financeiro@example.com", "cco_microsoft": "cco@example.com"}
    assert not env.exists()


def test_migrar_env_nao_sobrescreve_prefs(tmp_path):
    env = tmp_path / ".env"
    env.write_text('SMTP_USUARIO="outro@example.com"\nEMAIL_CCO="x@example.com"\n', encoding="utf-8")
    prefs = {"enviar_como": "financeiro@example.com", "cco_microsoft": ""}
    assert ef.migrar_env(prefs, env) is True
    assert prefs == {"enviar_como": "financeiro@example.com", "cco_microsoft": ""}
    assert not env.exists()


def test_migrar_env_sem_cco_apaga_mesmo_assim(tmp_path):
    env = tmp_path / ".env"
    env.write_text('SMTP_SENHA="x"\n', encoding="utf-8")
    prefs = {}
    assert ef.migrar_env(prefs, env) is True
    assert prefs == {} and not env.exists()


def test_migrar_env_sem_arquivo(tmp_path):
    assert ef.migrar_env({}, tmp_path / ".env") is False


def test_migrar_env_nao_poe_a_senha_no_ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("SMTP_SENHA", raising=False)
    env = tmp_path / ".env"
    env.write_text('SMTP_SENHA="segredo"\n', encoding="utf-8")
    ef.migrar_env({}, env)
    import os
    assert "SMTP_SENHA" not in os.environ


# --- envio ---------------------------------------------------------------------

def test_envia_como_remetente_logando_com_a_propria_conta(smtp):
    ef.Enviador(cfg(), ContaFalsa()).enviar(envio("a@example.com"), "financeiro@example.com", "c@example.com")
    assert smtp.login == ("eu@tcm.com", "T")
    assert smtp.from_addr == "financeiro@example.com"
    assert smtp.msg["From"] == "financeiro@example.com"
    assert smtp.to_addrs == ["a@example.com", "c@example.com"]
    assert "Bcc" not in smtp.msg  # CCO só no envelope


def test_sem_remetente_usa_a_propria_conta(smtp):
    ef.Enviador(cfg(), ContaFalsa()).enviar(envio(), "", "")
    assert smtp.from_addr == "eu@tcm.com"


def test_uma_conexao_por_lote(smtp, monkeypatch):
    aberturas = []
    original = microsoft.abrir_smtp
    monkeypatch.setattr(microsoft, "abrir_smtp", lambda e, t: aberturas.append(e) or original(e, t))
    enviador = ef.Enviador(cfg(), ContaFalsa())
    enviador.enviar(envio(), "", "")
    enviador.enviar(envio("b@example.com"), "", "")
    assert len(aberturas) == 1


def test_send_as_negado_e_fatal_com_texto_do_spec(smtp):
    smtp.erro = smtplib.SMTPSenderRefused(550, b"5.7.60 SMTP; Client does not have permissions to send as "
                                               b"this sender. SendAsDenied", "financeiro@example.com")
    with pytest.raises(ef.ErroFatal) as e:
        ef.Enviador(cfg(), ContaFalsa()).enviar(envio(), "financeiro@example.com", "")
    assert str(e.value) == ("Sua conta não tem permissão para enviar como 'financeiro@example.com'. "
                            "Peça à TI a permissão 'Enviar como' nessa caixa.")


def test_sessao_expirada_e_fatal(smtp):
    conta = ContaFalsa(falha=FalhaLogin("Sua sessão expirou. Entre novamente com a Microsoft."))
    with pytest.raises(ef.ErroFatal, match="Conta de envio"):
        ef.Enviador(cfg(), conta).enviar(envio(), "", "")
    assert smtp.msg is None


def test_sem_conta_e_fatal(smtp):
    with pytest.raises(ef.ErroFatal, match="Conta de envio"):
        ef.Enviador(cfg(), None).enviar(envio(), "", "")


def test_conta_sem_login_e_fatal(smtp):
    with pytest.raises(ef.ErroFatal, match="Conta de envio"):
        ef.Enviador(cfg(), ContaFalsa(email=None)).enviar(envio(), "", "")


def test_reconecta_com_token_novo_se_o_servidor_cair(smtp, monkeypatch):
    tokens = iter(["T1", "T2"])
    conta = ContaFalsa()
    conta.token = lambda: next(tokens)
    quedas = [smtplib.SMTPServerDisconnected("caiu")]

    def enviar(msg, from_addr, to_addrs):
        if quedas:
            raise quedas.pop()
        smtp.msg = msg

    smtp.send_message = enviar
    ef.Enviador(cfg(), conta).enviar(envio(), "", "")
    assert smtp.login == ("eu@tcm.com", "T2") and smtp.msg is not None


def test_sessao_expirada_e_erro_de_sessao(smtp):
    conta = ContaFalsa(falha=FalhaLogin("Sua sessão expirou. Entre novamente com a Microsoft."))
    with pytest.raises(ef.ErroSessao):
        ef.Enviador(cfg(), conta).enviar(envio(), "", "")
