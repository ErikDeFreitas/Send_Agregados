"""Tela demonstrativa do Design System (dados fictícios).

Executar a partir da pasta do projeto:  python design_system/main.py
"""
import sys
from pathlib import Path

if __package__ in (None, ""):  # permite rodar o arquivo direto
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QMainWindow, QMenu, QStackedWidget, QVBoxLayout, QWidget,
)

from design_system.components import (
    AreaTexto, BarraLateral, BarraProgresso, Botao, BotaoTema, Cabecalho, CaixaSelecao, Campo,
    CampoPesquisa, CampoTexto, Cartao, CartaoIndicador, Etiqueta, GradeResponsiva, Modal, Pagina,
    Selecao, Tabela, Texto,
)
from design_system.themes import ESPACO, tema

AGREGADOS = [  # fictícios
    ("Transportes Alfa Ltda", "**.***.***/0001-12", 6, "R$ 8.420,00", ("Enviado", "sucesso")),
    ("João Exemplo da Silva", "***.***.***-34", 3, "R$ 2.150,50", ("Pendente", "neutro")),
    ("Beta Logística ME", "**.***.***/0001-56", 9, "R$ 12.980,75", ("Enviando", "primaria")),
    ("Maria Fictícia Souza", "***.***.***-78", 2, "R$ 1.300,00", ("Falhou", "perigo")),
    ("Gama Cargas Eireli", "**.***.***/0001-90", 5, "R$ 6.775,20", ("Pendente", "neutro")),
    ("Delta Fretes Ltda", "**.***.***/0001-11", 4, "R$ 4.010,00", ("Enviado", "sucesso")),
]

PAGINAS = {
    "painel": ("Painel", "Envio semanal de extratos de fretes"),
    "componentes": ("Componentes", "Catálogo do Design System"),
    "config": ("Configurações", "Preferências do aplicativo"),
}


class JanelaDemo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoboAgregado – Design System")
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)

        self.barra = BarraLateral("RoboAgregado")
        self.barra.adicionar_item("painel", "Painel", "painel")
        self.barra.adicionar_item("componentes", "Componentes", "componentes")
        self.barra.adicionar_item("config", "Configurações", "config")
        self.barra.adicionar_rodape(Texto("Versão de demonstração", "dica"))
        self.barra.navegou.connect(self._ir_para)

        self.cabecalho = Cabecalho()
        self.cabecalho.adicionar(Botao("Credenciais", "secundario", "sm", icone="chave"))
        self.cabecalho.adicionar(BotaoTema())

        self.paginas = QStackedWidget()
        self._indices = {}
        for chave, criar in (("painel", self._pagina_painel), ("componentes", self._pagina_componentes),
                             ("config", self._pagina_config)):
            self._indices[chave] = self.paginas.addWidget(criar())

        direita = QVBoxLayout()
        direita.setContentsMargins(0, 0, 0, 0)
        direita.setSpacing(0)
        direita.addWidget(self.cabecalho)
        direita.addWidget(self.paginas, 1)
        raiz = QHBoxLayout()
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self.barra)
        raiz.addLayout(direita, 1)
        central = QWidget()
        central.setLayout(raiz)
        self.setCentralWidget(central)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo_envio)
        self._ir_para("painel")

    def _ir_para(self, chave: str):
        self.paginas.setCurrentIndex(self._indices[chave])
        self.cabecalho.definir_titulo(*PAGINAS[chave])

    # ------------------------------------------------------------ Painel
    def _pagina_painel(self) -> QWidget:
        pagina = Pagina()

        indicadores = GradeResponsiva(200)
        indicadores.adicionar(CartaoIndicador("Agregados na planilha", "24", "usuarios", "primaria"))
        indicadores.adicionar(CartaoIndicador("Fretes da semana", "87", "arquivo", "neutro"))
        self.ind_enviados = CartaoIndicador("Enviados", "0", "enviar", "sucesso")
        indicadores.adicionar(self.ind_enviados)
        indicadores.adicionar(CartaoIndicador("Falhas", "1", "alerta", "perigo"))
        pagina.conteudo.addWidget(indicadores)

        envio = Cartao("Novo envio", "Selecione a planilha e confira as opções antes de enviar.")
        grade = QGridLayout()
        grade.setHorizontalSpacing(ESPACO["lg"])
        grade.setVerticalSpacing(ESPACO["lg"])
        linha_planilha = QHBoxLayout()
        linha_planilha.setSpacing(ESPACO["sm"])
        planilha = CampoTexto("Nenhuma planilha selecionada")
        planilha.setReadOnly(True)
        linha_planilha.addWidget(planilha, 1)
        selecionar = Botao("Selecionar...", "secundario", icone="pasta")
        selecionar.clicked.connect(lambda: planilha.setText("Modelo Padrão.xlsx"))
        linha_planilha.addWidget(selecionar)
        caixa_planilha = QWidget()
        caixa_planilha.setLayout(linha_planilha)
        linha_planilha.setContentsMargins(0, 0, 0, 0)
        grade.addWidget(Campo("Planilha", caixa_planilha), 0, 0, 1, 2)
        self.campo_cco = Campo("Cópia oculta (CCO)", CampoTexto("email@empresa.com.br"),
                               "Opcional. Separe vários com ;")
        grade.addWidget(self.campo_cco, 1, 0)
        grade.addWidget(Campo("Intervalo entre envios",
                              Selecao(["5 segundos", "10 segundos", "30 segundos", "Sem intervalo"]),
                              "Evita bloqueio do servidor de e-mail"), 1, 1)
        grade.addWidget(Campo("Observação interna", AreaTexto("Anotações sobre este lote (não vai no e-mail)")),
                        2, 0, 1, 2)
        grade.addWidget(CaixaSelecao("Perguntar antes de reenviar extratos já enviados", True), 3, 0, 1, 2)
        grade.setColumnStretch(0, 1)
        grade.setColumnStretch(1, 1)
        envio.corpo.addLayout(grade)

        self.progresso = BarraProgresso()
        self.progresso.setRange(0, len(AGREGADOS))
        self.progresso.setValue(0)
        self.texto_progresso = Texto(f"0 de {len(AGREGADOS)} enviados", "dica")
        envio.corpo.addWidget(self.progresso)
        acoes = QHBoxLayout()
        acoes.setSpacing(ESPACO["sm"])
        acoes.addWidget(self.texto_progresso, 1)
        acoes.addWidget(Botao("Visualizar e-mail", "secundario", icone="olho"))
        self.btn_parar = Botao("Parar", "perigo", icone="parar")
        self.btn_parar.setEnabled(False)
        self.btn_parar.clicked.connect(self._parar_envio)
        acoes.addWidget(self.btn_parar)
        self.btn_enviar = Botao("Enviar selecionados", "primario", icone="enviar")
        self.btn_enviar.clicked.connect(self._confirmar_envio)
        acoes.addWidget(self.btn_enviar)
        envio.corpo.addLayout(acoes)
        pagina.conteudo.addWidget(envio)

        lista = Cartao("Agregados", "Lidos da aba VW da planilha")
        pesquisa = CampoPesquisa("Pesquisar agregado ou documento...")
        pesquisa.setMinimumWidth(260)
        lista.adicionar_acao(pesquisa)
        tabela = Tabela(["Agregado", "CPF / CNPJ", "Fretes", "Saldo", "Status"], alinhar_direita=(2, 3))
        for nome, doc, fretes, saldo, (status, tom) in AGREGADOS:
            tabela.adicionar_linha([nome, doc, fretes, saldo, Etiqueta(status, tom)])
        tabela.setMinimumHeight(44 * len(AGREGADOS) + 44)
        pesquisa.textChanged.connect(tabela.filtrar)
        lista.corpo.addWidget(tabela)
        pagina.conteudo.addWidget(lista)
        pagina.conteudo.addStretch(1)
        return pagina

    def _confirmar_envio(self):
        cco = self.campo_cco.controle.text().strip()
        if cco and "@" not in cco:
            self.campo_cco.definir_erro("Endereço de e-mail inválido")
            return
        self.campo_cco.definir_erro(None)
        if Modal.confirmar(self, "Enviar extratos?",
                           f"Serão enviados {len(AGREGADOS)} e-mails, um por agregado. "
                           "Esta é só uma demonstração: nada será enviado de verdade.",
                           "Enviar agora"):
            self.progresso.setValue(0)
            self.btn_enviar.setEnabled(False)
            self.btn_parar.setEnabled(True)
            self._timer.start(600)

    def _passo_envio(self):
        valor = self.progresso.value() + 1
        self.progresso.setValue(valor)
        self.texto_progresso.setText(f"{valor} de {len(AGREGADOS)} enviados")
        self.ind_enviados.definir_valor(str(valor))
        if valor >= len(AGREGADOS):
            self._parar_envio()

    def _parar_envio(self):
        self._timer.stop()
        self.btn_enviar.setEnabled(True)
        self.btn_parar.setEnabled(False)

    # ------------------------------------------------------------ Componentes
    def _pagina_componentes(self) -> QWidget:
        pagina = Pagina()

        botoes = Cartao("Botões", "Variantes e tamanhos (32, 40 e 48 px)")
        for tamanho in ("sm", "md", "lg"):
            linha = QHBoxLayout()
            linha.setSpacing(ESPACO["sm"])
            linha.addWidget(Botao("Primário", "primario", tamanho, icone="enviar"))
            linha.addWidget(Botao("Secundário", "secundario", tamanho))
            linha.addWidget(Botao("Excluir", "perigo", tamanho))
            linha.addWidget(Botao("Fantasma", "fantasma", tamanho))
            linha.addWidget(Botao("", "secundario", tamanho, icone="config"))
            linha.addStretch(1)
            botoes.corpo.addLayout(linha)
        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["sm"])
        for variante in ("primario", "secundario", "perigo"):
            desabilitado = Botao("Desabilitado", variante)
            desabilitado.setEnabled(False)
            linha.addWidget(desabilitado)
        com_menu = Botao("Mais ações", "secundario")
        menu = QMenu(com_menu)
        menu.addAction("Abrir pasta de dados")
        menu.addAction("Exportar log")
        menu.addSeparator()
        menu.addAction("Limpar histórico")
        com_menu.setMenu(menu)
        linha.addWidget(com_menu)
        abrir_modal = Botao("Abrir modal", "secundario")
        abrir_modal.clicked.connect(lambda: Modal.confirmar(
            self, "Excluir histórico?", "Os registros de envio serão apagados. Esta ação não pode ser desfeita.",
            "Excluir", destrutivo=True))
        linha.addWidget(abrir_modal)
        linha.addStretch(1)
        botoes.corpo.addLayout(linha)
        pagina.conteudo.addWidget(botoes)

        campos = Cartao("Campos", "Altura 42 px, borda azul no foco")
        grade = QGridLayout()
        grade.setHorizontalSpacing(ESPACO["lg"])
        grade.setVerticalSpacing(ESPACO["lg"])
        grade.addWidget(Campo("Padrão", CampoTexto("Digite algo...")), 0, 0)
        desabilitado = CampoTexto("Indisponível")
        desabilitado.setEnabled(False)
        grade.addWidget(Campo("Desabilitado", desabilitado), 0, 1)
        com_erro = Campo("Com erro", CampoTexto("email@empresa"))
        com_erro.definir_erro("Endereço de e-mail inválido")
        grade.addWidget(com_erro, 1, 0)
        grade.addWidget(Campo("Pesquisa", CampoPesquisa()), 1, 1)
        grade.addWidget(Campo("Seleção", Selecao(["Opção A", "Opção B", "Opção C"])), 2, 0)
        checks = QVBoxLayout()
        checks.setSpacing(ESPACO["sm"])
        checks.addWidget(CaixaSelecao("Marcada", True))
        checks.addWidget(CaixaSelecao("Desmarcada"))
        bloqueada = CaixaSelecao("Desabilitada", True)
        bloqueada.setEnabled(False)
        checks.addWidget(bloqueada)
        caixa_checks = QWidget()
        caixa_checks.setLayout(checks)
        checks.setContentsMargins(0, 0, 0, 0)
        grade.addWidget(Campo("Checkbox", caixa_checks), 2, 1)
        grade.addWidget(Campo("Área de texto", AreaTexto("Mínimo de 100 px de altura")), 3, 0, 1, 2)
        grade.setColumnStretch(0, 1)
        grade.setColumnStretch(1, 1)
        campos.corpo.addLayout(grade)
        pagina.conteudo.addWidget(campos)

        etiquetas = Cartao("Etiquetas", "Status em tabelas e listas")
        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["sm"])
        for texto, tom in (("Enviado", "sucesso"), ("Enviando", "primaria"), ("Falhou", "perigo"),
                           ("Pendente", "neutro")):
            linha.addWidget(Etiqueta(texto, tom))
        linha.addStretch(1)
        etiquetas.corpo.addLayout(linha)
        pagina.conteudo.addWidget(etiquetas)
        pagina.conteudo.addStretch(1)
        return pagina

    # ------------------------------------------------------------ Configurações
    def _pagina_config(self) -> QWidget:
        pagina = Pagina()
        aparencia = Cartao("Aparência", "A preferência fica salva neste computador.")
        seletor = Selecao(["Claro", "Escuro"])
        seletor.setCurrentIndex(1 if tema.escuro else 0)
        seletor.currentIndexChanged.connect(lambda i: tema.definir("escuro" if i else "claro"))
        tema.mudou.connect(lambda nome: seletor.setCurrentIndex(1 if nome == "escuro" else 0))
        campo = Campo("Tema", seletor)
        campo.setMaximumWidth(320)
        aparencia.corpo.addWidget(campo)
        pagina.conteudo.addWidget(aparencia)
        pagina.conteudo.addStretch(1)
        return pagina


def main():
    app = QApplication(sys.argv)
    tema.aplicar(app)
    janela = JanelaDemo()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
