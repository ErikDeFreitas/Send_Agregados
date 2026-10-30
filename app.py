"""Tela do Extrato de Fretes: escolhe a planilha, confere os agregados e envia os e-mails."""

import html
import json
import os
import queue
import sys
import tempfile
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QMainWindow, QVBoxLayout, QWidget,
)

import atualizador
import enviar_fretes as ef
from design_system import icons
from design_system.components import (
    AreaLog, BarraLateral, BarraProgresso, Botao, BotaoTema, Cabecalho, Campo, CampoTexto, Cartao,
    CartaoIndicador, Etiqueta, GradeResponsiva, Modal, Pagina, Tabela, Texto,
)
from design_system.themes import ESPACO, MARCA, TAMANHOS, tema
from versao import VERSAO

ARQUIVO_PREFS = ef.PASTA / "preferencias.json"

# coluna "Status" da lista e tom da etiqueta para cada marcação usada pela thread de envio
COL_EMAIL, COL_STATUS = 4, 5
TOM_STATUS = {"": "primaria", "enviado": "sucesso", "erro": "perigo"}


def ler_prefs() -> dict:
    try:
        return json.loads(ARQUIVO_PREFS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_prefs(prefs: dict):
    try:
        ARQUIVO_PREFS.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


class DialogoCredenciais(Modal):
    """Pede usuário e senha do remetente, testa o login e grava no .env."""

    def __init__(self, pai, cfg):
        super().__init__("Credenciais do remetente",
                         "Informe o e-mail remetente e a senha da conta que enviará os extratos. "
                         "Os dados ficam salvos só neste computador (arquivo .env).", pai)
        self.cfg, self.salvo = cfg, False
        self.campo_usuario = CampoTexto("envios@empresa.com.br")
        self.campo_usuario.setText(os.environ.get("SMTP_USUARIO", ""))
        self.campo_senha = CampoTexto()
        self.campo_senha.setEchoMode(QLineEdit.Password)
        self.campo_cco = CampoTexto()
        self.campo_cco.setText(ef.cco_padrao(cfg))
        self.corpo.addSpacing(ESPACO["sm"])
        self.corpo.addWidget(Campo("E-mail", self.campo_usuario))
        self.corpo.addWidget(Campo("Senha", self.campo_senha))
        self.corpo.addWidget(Campo("CCO padrão", self.campo_cco, "Cópia oculta, opcional; vários separados por ;"))
        self.msg = Texto("", "erro")
        self.msg.setWordWrap(True)
        self.msg.hide()
        self.corpo.addWidget(self.msg)

        self.adicionar_botao(Botao("Cancelar", "secundario")).clicked.connect(self.reject)
        self.btn_salvar = self.adicionar_botao(Botao("Testar e salvar"))
        self.btn_salvar.clicked.connect(self.salvar)
        self.btn_salvar.setDefault(True)  # Enter salva; Esc fecha (padrão do QDialog)
        (self.campo_senha if self.campo_usuario.text() else self.campo_usuario).setFocus()

    def mensagem(self, texto: str, erro: bool = True):
        self.msg.setProperty("papel", "erro" if erro else "suave")
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)
        self.msg.setText(texto)
        self.msg.show()

    def salvar(self):
        usuario, senha = self.campo_usuario.text().strip(), self.campo_senha.text()
        cco = self.campo_cco.text().strip()
        if ef.emails_invalidos(usuario) or not usuario:
            self.mensagem("Informe um e-mail válido.")
            return
        if not senha:
            self.mensagem("Informe a senha.")
            return
        if ef.emails_invalidos(cco):
            self.mensagem(f"CCO inválido: {', '.join(ef.emails_invalidos(cco))}")
            return
        self.mensagem("Testando o login no servidor...", erro=False)
        self.btn_salvar.setEnabled(False)
        QApplication.processEvents()
        try:
            ef.testar_login(self.cfg, usuario, senha)
        except ef.ErroEnvio as e:
            self.mensagem(str(e))
            self.btn_salvar.setEnabled(True)
            return
        try:
            ef.salvar_env(usuario, senha, cco)
        except OSError:
            self.mensagem("Não foi possível gravar o arquivo .env nesta pasta. "
                          "Verifique a permissão de escrita na pasta de dados do programa.")
            self.btn_salvar.setEnabled(True)
            return
        self.salvo = True
        self.accept()


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = ef.carregar_config()
        self.prefs = ler_prefs()
        self.envios = {}
        self.linhas = {}  # doc -> linha da tabela
        self.status = {}  # doc -> marcação atual ("", "enviado", "erro")
        self.concluidos = set()
        self.fila = queue.Queue()
        self.enviando = False
        self.parar = threading.Event()

        # o remetente vem das credenciais (.env); só o método Outlook usa o enviar_como do config.ini
        self.metodo = self.cfg["email"].get("metodo", "outlook").strip().lower()
        self.chave_cco = f"cco_{self.metodo}"

        self.setWindowTitle(f"RoboAgregado - Extrato de Fretes (v{VERSAO})")
        self.setWindowIcon(icons.icone("caminhao", MARCA["primaria"], 32))
        self.resize(1200, 820)
        self.setMinimumSize(900, 600)

        barra = BarraLateral("RoboAgregado")
        barra.adicionar_item("extrato", "Extrato de fretes", "enviar")
        if self.metodo == "smtp":
            credenciais = Botao("Credenciais...", "secundario", icone="chave")
            credenciais.clicked.connect(self.pedir_credenciais)
            barra.adicionar_rodape(credenciais)
        pasta = Botao("Pasta de dados", "secundario", icone="pasta")
        pasta.clicked.connect(lambda: os.startfile(ef.PASTA))
        barra.adicionar_rodape(pasta)
        barra.adicionar_rodape(Texto(f"Versão {VERSAO}", "dica"))

        cabecalho = Cabecalho("Extrato de fretes", "Envio dos extratos semanais aos agregados")
        cabecalho.adicionar(BotaoTema())

        pagina = Pagina()
        pagina.conteudo.addWidget(self._indicadores())
        pagina.conteudo.addWidget(self._cartao_configuracao())
        pagina.conteudo.addWidget(self._cartao_agregados(), 1)
        registro = Cartao("Registro")
        self.log = AreaLog()
        self.log.setFixedHeight(150)
        registro.corpo.addWidget(self.log)
        pagina.conteudo.addWidget(registro)

        direita = QVBoxLayout()
        direita.setContentsMargins(0, 0, 0, 0)
        direita.setSpacing(0)
        direita.addWidget(cabecalho)
        direita.addWidget(pagina, 1)
        raiz = QHBoxLayout()
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(barra)
        raiz.addLayout(direita, 1)
        central = QWidget()
        central.setLayout(raiz)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.processar_fila)
        self.timer.start(150)
        if self.metodo == "smtp" and not ef.credenciais_ok():
            QTimer.singleShot(300, self.pedir_credenciais)  # primeira execução
        QTimer.singleShot(1000, self.verificar_atualizacao)

    # -------------------------------------------------------------- montagem da tela

    def _indicadores(self) -> QWidget:
        grade = GradeResponsiva(200)
        self.ind_agregados = CartaoIndicador("Agregados", "–", "usuarios", "primaria")
        self.ind_sem_email = CartaoIndicador("Sem e-mail", "–", "alerta", "neutro")
        self.ind_enviados = CartaoIndicador("Enviados", "–", "enviar", "sucesso")
        self.ind_erros = CartaoIndicador("Com erro", "–", "alerta", "perigo")
        for cartao in (self.ind_agregados, self.ind_sem_email, self.ind_enviados, self.ind_erros):
            grade.adicionar(cartao)
        return grade

    def _cartao_configuracao(self) -> QWidget:
        cartao = Cartao("Configuração do envio")
        grade = QGridLayout()
        grade.setHorizontalSpacing(ESPACO["lg"])
        grade.setVerticalSpacing(ESPACO["lg"])

        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(ESPACO["sm"])
        self.campo_planilha = CampoTexto("Nenhuma planilha selecionada")
        self.campo_planilha.setReadOnly(True)
        linha.addWidget(self.campo_planilha, 1)
        selecionar = Botao("Selecionar planilha...", "secundario", icone="pasta")
        selecionar.clicked.connect(self.selecionar_planilha)
        linha.addWidget(selecionar)
        caixa = QWidget()
        caixa.setLayout(linha)
        grade.addWidget(Campo("Planilha", caixa), 0, 0, 1, 2)

        self.campo_cco = CampoTexto("email@empresa.com.br")
        self.campo_cco.setText(self.prefs.get(self.chave_cco, ef.cco_padrao(self.cfg)))
        grade.addWidget(Campo("Cópia oculta (CCO)", self.campo_cco, "Separe vários com ;"), 1, 0)
        self.campo_intervalo = CampoTexto()
        self.campo_intervalo.setText(str(
            self.prefs.get("intervalo", self.cfg["email"].get("intervalo_segundos", "5"))))
        grade.addWidget(Campo("Intervalo (s)", self.campo_intervalo, "Espera entre um envio e outro"), 1, 1)
        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
        cartao.corpo.addLayout(grade)
        return cartao

    def _cartao_agregados(self) -> QWidget:
        self.cartao_lista = Cartao("Agregados", "Selecione a planilha para começar.")
        todos = Botao("Selecionar todos", "secundario", "sm")
        self.cartao_lista.adicionar_acao(todos)

        self.tabela = Tabela(["CNPJ/CPF", "Agregado", "Fretes", "Total", "E-mail", "Status"],
                             alinhar_direita=(2, 3), coluna_flexivel=1)
        self.tabela.setMinimumHeight(TAMANHOS["linha_tabela"] * 6 + TAMANHOS["cabecalho_tabela"])
        self.tabela.doubleClicked.connect(lambda _: self.visualizar())
        todos.clicked.connect(self.tabela.selectAll)
        self.cartao_lista.corpo.addWidget(self.tabela, 1)

        self.progresso = BarraProgresso()
        self.progresso.setValue(0)
        self.cartao_lista.corpo.addWidget(self.progresso)
        acoes = QHBoxLayout()
        acoes.setSpacing(ESPACO["sm"])
        self.texto_progresso = Texto("", "dica")
        acoes.addWidget(self.texto_progresso, 1)
        visualizar = Botao("Visualizar e-mail", "secundario", icone="olho")
        visualizar.clicked.connect(self.visualizar)
        acoes.addWidget(visualizar)
        self.btn_parar = Botao("Parar", "perigo", icone="parar")
        self.btn_parar.setEnabled(False)
        self.btn_parar.clicked.connect(self.parar_envio)
        acoes.addWidget(self.btn_parar)
        self.btn_enviar = Botao("Enviar selecionados", icone="enviar")
        self.btn_enviar.clicked.connect(self.enviar_selecionados)
        acoes.addWidget(self.btn_enviar)
        self.cartao_lista.corpo.addLayout(acoes)
        return self.cartao_lista

    # -------------------------------------------------------------- atualização

    def verificar_atualizacao(self):
        """Ao abrir, procura uma Release mais nova no GitHub (só no executável, em segundo plano)."""
        if not getattr(sys, "frozen", False):
            return
        cfg = self.cfg["atualizacao"] if self.cfg.has_section("atualizacao") else {}
        if str(cfg.get("ativo", "sim")).strip().lower() not in ("sim", "s", "true", "1"):
            return
        atualizador.limpar_temporarios()
        repositorio = str(cfg.get("repositorio", "ErikDeFreitas/Send_Agregados")).strip()
        threading.Thread(target=self._atualizar_thread, args=(repositorio,), daemon=True).start()

    def _atualizar_thread(self, repositorio):
        try:
            info = atualizador.buscar_atualizacao(repositorio)
            if not info:
                return
            self.fila.put(("log", f"Nova versão {info['versao']} encontrada. Baixando..."))
            novo = Path(sys.executable)
            novo = novo.with_name(novo.name + ".novo")
            atualizador.baixar_e_verificar(info, novo)
            self.fila.put(("atualizar", info["versao"], str(novo)))
        except atualizador.ErroAtualizacao as e:
            self.fila.put(("log", f"Atualização automática não realizada: {e}"))
        except Exception as e:
            self.fila.put(("log", f"Atualização automática não realizada ({type(e).__name__})."))

    def _aplicar_atualizacao(self, versao, caminho):
        novo = Path(caminho)
        if self.enviando:  # nunca troca o programa no meio de um envio
            novo.unlink(missing_ok=True)
            self.escrever_log("Atualização adiada: há um envio em andamento. Será tentada na próxima abertura.")
            return
        Modal.informar(self, "Atualização", f"Nova versão {versao} instalada.\n"
                                            "O programa será reiniciado agora.", "sucesso")
        try:
            atualizador.aplicar_e_reiniciar(novo)
        except atualizador.ErroAtualizacao as e:
            novo.unlink(missing_ok=True)
            Modal.informar(self, "Atualização", f"{e}\nO programa continuará na versão atual.", "perigo")
            return
        self.close()
        os._exit(0)

    # -------------------------------------------------------------- ações

    def pedir_credenciais(self) -> bool:
        dialogo = DialogoCredenciais(self, self.cfg)
        dialogo.exec()
        if dialogo.salvo:
            self.campo_cco.setText(os.environ.get("EMAIL_CCO", ""))
            self.escrever_log(f"Credenciais salvas para {os.environ.get('SMTP_USUARIO')}.")
        return dialogo.salvo

    def escrever_log(self, texto):
        self.log.escrever(texto)

    def selecionar_planilha(self):
        pasta = Path(self.prefs.get("planilha", "")).parent if self.prefs.get("planilha") else None
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecione a planilha de fretes", str(pasta) if pasta and pasta.exists() else "",
            "Planilhas Excel (*.xlsx *.xlsm);;Todos os arquivos (*.*)")
        if caminho:
            self.carregar(str(Path(caminho)))

    def carregar(self, caminho):
        try:
            df, emails = ef.carregar_dados(self.cfg, caminho)
            envios = ef.preparar_envios(self.cfg, df, emails,
                                        periodo_fixo=self.cfg["email"].get("periodo", ""))
        except ef.ErroPlanilha as e:
            Modal.informar(self, "Planilha inválida", str(e), "perigo")
            return
        except PermissionError:
            Modal.informar(self, "Planilha em uso",
                           "Não foi possível ler a planilha. Feche-a no Excel e tente novamente.", "perigo")
            return
        except Exception as e:
            Modal.informar(self, "Erro ao ler a planilha", f"{type(e).__name__}: {e}", "perigo")
            return

        self.campo_planilha.setText(caminho)
        self.prefs["planilha"] = caminho
        salvar_prefs(self.prefs)
        self.tabela.setRowCount(0)
        self.envios = {e["doc"]: e for e in envios}
        self.linhas, self.status = {}, {}
        sem_email = 0
        for e in envios:
            if not e["email"]:
                sem_email += 1
            linha = self.tabela.adicionar_linha([
                ef.formatar_documento(e["doc"]), e["nome"], e["fretes"],
                ef.formatar_moeda(e["total"]) if e.get("total") is not None else "",
                e["email"] or "SEM E-MAIL", ""])
            if not e["email"]:
                self.tabela.item(linha, COL_EMAIL).setForeground(QColor(MARCA["perigo"]))
            self.linhas[e["doc"]] = linha
        self.tabela.clearSelection()
        for doc, e in self.envios.items():
            if e["email"]:
                self._selecionar_linha(self.linhas[doc])
        resumo = f"{len(envios)} agregado(s) encontrados"
        if sem_email:
            resumo += f" | {sem_email} sem e-mail"
        self.cartao_lista.definir_subtitulo(resumo)
        self.ind_agregados.definir_valor(str(len(envios)))
        self.ind_sem_email.definir_valor(str(sem_email))
        self._atualizar_contadores()
        self.progresso.setValue(0)
        self.texto_progresso.setText("")
        self.escrever_log(f"Planilha carregada: {caminho} ({len(envios)} agregados)")

    def _selecionar_linha(self, linha):
        """Acrescenta a linha à seleção (selectRow trocaria a seleção inteira)."""
        modelo = self.tabela.selectionModel()
        modelo.select(self.tabela.model().index(linha, 0),
                      QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _selecionados(self) -> list:
        """Documentos das linhas selecionadas, na ordem da lista."""
        por_linha = {linha: doc for doc, linha in self.linhas.items()}
        linhas = sorted(i.row() for i in self.tabela.selectionModel().selectedRows())
        return [por_linha[l] for l in linhas]

    def _atualizar_contadores(self):
        self.ind_enviados.definir_valor(str(sum(1 for t in self.status.values() if t == "enviado")))
        self.ind_erros.definir_valor(str(sum(1 for t in self.status.values() if t == "erro")))

    def visualizar(self):
        sel = self._selecionados()
        if not sel:
            Modal.informar(self, "Visualizar", "Selecione um agregado na lista.")
            return
        e = self.envios[sel[0]]
        cco = self.campo_cco.text().strip()
        cabecalho = (f'<div style="font-family:Segoe UI,Arial;font-size:13px;background:#f4f4f4;'
                     f'padding:10px;margin-bottom:15px;border:1px solid #ddd">'
                     f'<b>Para:</b> {html.escape(e["email"] or "SEM E-MAIL")}<br>'
                     f'<b>CCO:</b> {html.escape(cco or "-")}<br>'
                     f'<b>Assunto:</b> {html.escape(e["assunto"])}</div>')
        # cabeçalho só na prévia, logo após a tag <body ...>
        corpo = e["corpo"]
        i = corpo.find(">", corpo.find("<body")) + 1
        arq = Path(tempfile.gettempdir()) / f"previa_{e['doc']}.html"
        arq.write_text(corpo[:i] + cabecalho + corpo[i:], encoding="utf-8")
        webbrowser.open(arq.as_uri())

    def enviar_selecionados(self):
        if self.enviando:
            return
        if self.metodo == "smtp" and not ef.credenciais_ok() and not self.pedir_credenciais():
            return
        selecionados = [self.envios[d] for d in self._selecionados()]
        if not selecionados:
            Modal.informar(self, "Enviar", "Selecione ao menos um agregado na lista.")
            return
        sem_email = [e for e in selecionados if not e["email"]]
        validos = [e for e in selecionados if e["email"]]
        if not validos:
            Modal.informar(self, "Enviar", "Nenhum dos selecionados tem e-mail cadastrado.", "perigo")
            return

        remetente = self.cfg["email"].get("enviar_como", "").strip() if self.metodo == "outlook" else ""
        cco = self.campo_cco.text().strip()
        try:
            intervalo = max(0.0, float(self.campo_intervalo.text().replace(",", ".")))
        except ValueError:
            Modal.informar(self, "Intervalo", "Informe o intervalo em segundos (ex.: 5).", "perigo")
            return

        # validação dos endereços antes de enviar qualquer coisa
        problemas = ef.emails_invalidos(remetente) + ef.emails_invalidos(cco)
        if problemas:
            Modal.informar(self, "E-mail inválido", "Corrija o remetente/CCO:\n" + "\n".join(problemas), "perigo")
            return
        invalidos = [e for e in validos if ef.emails_invalidos(e["email"])]
        if invalidos:
            lista_inv = "\n".join(f"{e['nome']}: {e['email']}" for e in invalidos[:10])
            if not Modal.confirmar(
                    self, "E-mails inválidos",
                    f"{len(invalidos)} agregado(s) com e-mail inválido na planilha:\n\n{lista_inv}"
                    "\n\nContinuar enviando apenas para os demais?", "Continuar", tom="perigo"):
                return
            validos = [e for e in validos if e not in invalidos]
            if not validos:
                return

        # prevenção de duplicidade: mesmo extrato (agregado + assunto) já enviado
        anteriores = ef.envios_anteriores()
        repetidos = [(e, ef.ja_enviado(e, anteriores)) for e in validos if ef.ja_enviado(e, anteriores)]
        if repetidos:
            lista_rep = "\n".join(f"{e['nome']} (em {quando})" for e, quando in repetidos[:10])
            resp = Modal.escolher(
                self, "Extrato já enviado",
                f"{len(repetidos)} agregado(s) já receberam este mesmo extrato:\n\n{lista_rep}",
                [("Cancelar", "secundario", None),
                 ("Reenviar para eles também", "secundario", True),
                 ("Só para quem não recebeu", "primario", False)], tom="perigo")
            if resp is None:
                return
            if resp is False:
                ja = {e["doc"] for e, _ in repetidos}
                validos = [e for e in validos if e["doc"] not in ja]
                if not validos:
                    Modal.informar(self, "Enviar", "Todos os selecionados já receberam este extrato.")
                    return

        rotulo_rem = remetente or ef.remetente_padrao(self.cfg) or "e-mail logado no Outlook"
        texto = (f"Enviar {len(validos)} e-mail(s)?\n\n"
                 f"Remetente: {rotulo_rem}\n"
                 f"Cópia oculta (CCO): {cco or '-'}\n"
                 f"Intervalo entre envios: {intervalo:g} s")
        if sem_email:
            texto += f"\n\n{len(sem_email)} selecionado(s) sem e-mail serão ignorados."
        if remetente and self.metodo == "outlook":
            texto += ("\n\nComo há remetente definido, o primeiro e-mail será verificado antes "
                      "de continuar (cerca de 20 s).")
        if not Modal.confirmar(self, "Confirmar envio", texto, "Enviar", tom="info"):
            return

        self.prefs.update({self.chave_cco: cco, "intervalo": f"{intervalo:g}"})
        salvar_prefs(self.prefs)
        self.enviando = True
        self.parar.clear()
        self.btn_enviar.setEnabled(False)
        self.btn_parar.setEnabled(True)
        self.concluidos = set()
        self.progresso.setRange(0, len(validos))
        self.progresso.setValue(0)
        self.texto_progresso.setText(f"0 de {len(validos)} processados")
        envios = [dict(e) for e in validos]  # cópia: marcações de recusa não afetam a lista
        threading.Thread(target=self._enviar_thread, args=(envios, remetente, cco, intervalo),
                         daemon=True).start()

    def parar_envio(self):
        self.parar.set()
        self.btn_parar.setEnabled(False)
        self.escrever_log("Parando após o envio atual...")

    def _aguardar_recusas(self, inicio, envios, espera) -> bool:
        """Consulta a Caixa de Entrada por avisos de não entrega; marca os recusados."""
        limite = time.monotonic() + espera
        pendentes = list(envios)
        achou = False
        while pendentes and time.monotonic() < limite:
            if self.parar.wait(4):
                break
            recusas = ef.buscar_recusas(inicio, [e["assunto"] for e in pendentes])
            for e in [e for e in pendentes if e["assunto"] in recusas]:
                e["recusado"] = recusas[e["assunto"]]
                ef.registrar_log(e["doc"], e["nome"], e["email"], f"RECUSADO: {e['recusado']}",
                                 e["assunto"])
                self.fila.put(("status", e["doc"], "Recusado", "erro"))
                self.fila.put(("log", f"[RECUSADO] {e['nome']} -> {e['email']}: {e['recusado']}"))
                pendentes.remove(e)
                achou = True
        return achou

    def _enviar_thread(self, envios, remetente, cco, intervalo):
        outlook = self.metodo == "outlook"
        if outlook:
            import pythoncom  # o Outlook (COM) precisa ser inicializado em cada thread
            pythoncom.CoInitialize()
        inicio = datetime.now()
        enviados, falhas, aviso = [], 0, ""
        enviador = ef.Enviador(self.cfg)
        try:
            for e in envios:
                if self.parar.is_set() or (enviados and self.parar.wait(intervalo)):
                    aviso = "Envio interrompido pelo usuário."
                    break
                self.fila.put(("status", e["doc"], "Enviando...", ""))
                try:
                    enviador.enviar(e, remetente, cco)
                    ef.registrar_log(e["doc"], e["nome"], e["email"], "ENVIADO", e["assunto"])
                    self.fila.put(("status", e["doc"], "Enviado", "enviado"))
                    self.fila.put(("log", f"[ENVIADO] {e['nome']} -> {e['email']}"))
                    enviados.append(e)
                except Exception as erro:
                    if not isinstance(erro, ef.ErroEnvio):  # nunca exibe detalhes internos
                        erro = ef.ErroEnvio(f"Erro inesperado ({type(erro).__name__}).")
                    ef.registrar_log(e["doc"], e["nome"], e["email"], f"ERRO: {erro}", e["assunto"])
                    self.fila.put(("status", e["doc"], "Erro", "erro"))
                    self.fila.put(("log", f"[ERRO] {e['nome']} -> {e['email']}: {erro}"))
                    falhas += 1
                    if isinstance(erro, ef.ErroFatal):
                        aviso = f"{erro}\n\nO envio foi interrompido, pois o erro afeta todos os e-mails."
                        break
                    continue

                # com remetente definido, confirma no 1º envio se o servidor aceitou
                if outlook and remetente and len(enviados) == 1:
                    self.fila.put(("status", e["doc"], "Verificando...", ""))
                    self.fila.put(("log", f"Verificando se o servidor aceitou o remetente {remetente}..."))
                    if self._aguardar_recusas(inicio, [e], ef.ESPERA_RECUSAS):
                        aviso = (f"O servidor recusou o envio como '{remetente}':\n{e['recusado']}\n\n"
                                 "Os demais e-mails não foram enviados. Verifique a permissão com a TI "
                                 "ou revise o método de envio.")
                        break
                    self.fila.put(("status", e["doc"], "Enviado", "enviado"))

            restantes = [e for e in enviados if "recusado" not in e]
            if outlook and restantes and not self.parar.is_set():
                self.fila.put(("log", f"Aguardando {ef.ESPERA_RECUSAS}s por avisos de não entrega..."))
                self._aguardar_recusas(inicio, restantes, ef.ESPERA_RECUSAS)
        finally:
            enviador.fechar()
            if outlook:
                pythoncom.CoUninitialize()
            recusados = sum(1 for e in enviados if "recusado" in e)
            self.fila.put(("fim", len(enviados) - recusados, falhas + recusados, aviso))

    def _marcar_status(self, doc, status, tag):
        self.tabela.definir_celula(self.linhas[doc], COL_STATUS, Etiqueta(status, TOM_STATUS.get(tag, "neutro")))
        self.status[doc] = tag
        if tag in ("enviado", "erro") and doc not in self.concluidos:
            self.concluidos.add(doc)
            self.progresso.setValue(len(self.concluidos))
            self.texto_progresso.setText(f"{len(self.concluidos)} de {self.progresso.maximum()} processados")
        self._atualizar_contadores()

    def processar_fila(self):
        # pausa o timer enquanto processa: as janelas de aviso abaixo rodam o loop de eventos
        self.timer.stop()
        try:
            while True:
                item = self.fila.get_nowait()
                if item[0] == "status":
                    _, doc, status, tag = item
                    self._marcar_status(doc, status, tag)
                elif item[0] == "log":
                    self.escrever_log(item[1])
                elif item[0] == "atualizar":
                    self._aplicar_atualizacao(item[1], item[2])
                elif item[0] == "fim":
                    _, ok, falhas, aviso = item
                    self.enviando = False
                    self.btn_enviar.setEnabled(True)
                    self.btn_parar.setEnabled(False)
                    self.escrever_log(f"Concluído: {ok} enviado(s), {falhas} com erro/recusado.")
                    resumo = f"{ok} e-mail(s) enviado(s)\n{falhas} com erro ou recusado(s)"
                    if aviso:
                        Modal.informar(self, "Envio interrompido", f"{aviso}\n\n{resumo}", "perigo")
                    else:
                        Modal.informar(self, "Envio concluído", resumo, "sucesso")
        except queue.Empty:
            pass
        finally:
            self.timer.start(150)


if __name__ == "__main__":
    aplicacao = QApplication(sys.argv)
    tema.aplicar(aplicacao)
    janela = App()
    janela.show()
    sys.exit(aplicacao.exec())
