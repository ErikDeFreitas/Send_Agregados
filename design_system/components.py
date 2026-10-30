"""Componentes reutilizáveis do Design System.

O visual fica todo em styles.qss; aqui só se definem estrutura, tamanhos (tokens de themes.py)
e as propriedades que o QSS usa para escolher o estilo (variante, tamanho, papel, tom...).
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListView, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import icons
from .themes import ESPACO, TAMANHOS, tema


def repolir(widget: QWidget):
    """Reaplica o QSS depois de mudar uma propriedade dinâmica."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# ---------------------------------------------------------------- textos

class Texto(QLabel):
    """Rótulo com papel tipográfico: titulo, subtitulo, rotulo, dica, suave, erro, valor, marca."""

    def __init__(self, texto: str = "", papel: str | None = None, parent=None):
        super().__init__(texto, parent)
        if papel:
            self.setProperty("papel", papel)


class Etiqueta(QLabel):
    """Badge de status. tom: primaria, sucesso, perigo, neutro."""

    def __init__(self, texto: str, tom: str = "neutro", parent=None):
        super().__init__(texto, parent)
        self.setProperty("etiqueta", True)
        self.setProperty("tom", tom)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # não estica na linha da tabela

    def sizeHint(self) -> QSize:
        # o QLabel não soma o padding do QSS ao próprio tamanho; calcula aqui
        self.ensurePolished()
        largura = self.fontMetrics().horizontalAdvance(self.text()) + 2 * TAMANHOS["etiqueta_padding"] + 2
        return QSize(largura, TAMANHOS["etiqueta_altura"])

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def definir(self, texto: str, tom: str):
        self.setText(texto)
        self.setProperty("tom", tom)
        repolir(self)
        self.updateGeometry()


# ---------------------------------------------------------------- botões

class Botao(QPushButton):
    """variante: primario, secundario, perigo, fantasma · tamanho: sm, md, lg."""

    _COR_ICONE = {"primario": "branco", "perigo": "branco", "secundario": "texto", "fantasma": "texto_suave"}

    def __init__(self, texto: str = "", variante: str = "primario", tamanho: str = "md",
                 icone: str | None = None, parent=None):
        # o Qt não tem espaçamento configurável entre ícone e texto; um espaço resolve
        super().__init__(f" {texto}" if icone and texto else texto, parent)
        self.setProperty("variante", variante)
        self.setProperty("tamanho", tamanho)
        self.setFixedHeight(TAMANHOS[f"botao_{tamanho}"])
        self.setCursor(Qt.PointingHandCursor)
        lado = TAMANHOS["icone_lg"] if tamanho == "lg" else TAMANHOS["icone"]
        self.setIconSize(QSize(lado, lado))
        if not texto:  # botão só com ícone fica quadrado
            self.setProperty("so_icone", True)
            self.setFixedWidth(TAMANHOS[f"botao_{tamanho}"])
        self._icone = icone
        tema.mudou.connect(self._pintar_icone)
        self._pintar_icone()

    def definir_icone(self, nome: str | None):
        self._icone = nome
        self._pintar_icone()

    def setMenu(self, menu):
        super().setMenu(menu)
        self.setProperty("com_menu", menu is not None)
        repolir(self)

    def _pintar_icone(self, *_):
        if not self._icone:
            return
        cores = tema.tokens()
        token = self._COR_ICONE[self.property("variante")]
        cor_desab = cores["branco"] if token == "branco" else cores["desab_texto"]
        self.setIcon(icons.icone(self._icone, cores[token], self.iconSize().width(), cor_desab))


class BotaoTema(Botao):
    """Alterna entre claro e escuro; mostra a lua no claro e o sol no escuro."""

    def __init__(self, parent=None):
        super().__init__("", "fantasma", "md", parent=parent)
        self.clicked.connect(tema.alternar)
        tema.mudou.connect(self._atualizar)
        self._atualizar()

    def _atualizar(self, *_):
        self.definir_icone("sol" if tema.escuro else "lua")
        self.setToolTip("Usar tema claro" if tema.escuro else "Usar tema escuro")


# ---------------------------------------------------------------- campos

class CampoTexto(QLineEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(TAMANHOS["campo"])


class CampoPesquisa(CampoTexto):
    def __init__(self, placeholder: str = "Pesquisar...", parent=None):
        super().__init__(placeholder, parent)
        self._acao = self.addAction(icons.icone("pesquisa", "#000"), QLineEdit.LeadingPosition)
        tema.mudou.connect(self._pintar_icone)
        self._pintar_icone()

    def _pintar_icone(self, *_):
        self._acao.setIcon(icons.icone("pesquisa", tema.tokens()["texto_suave"], TAMANHOS["icone"]))


class Selecao(QComboBox):
    def __init__(self, itens=(), parent=None):
        super().__init__(parent)
        self.setView(QListView())  # necessário para o QSS estilizar os itens da lista
        self.addItems(list(itens))
        self.setFixedHeight(TAMANHOS["campo"])
        self.setCursor(Qt.PointingHandCursor)


class AreaTexto(QPlainTextEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(TAMANHOS["area_texto_min"])


class CaixaSelecao(QCheckBox):
    def __init__(self, texto: str = "", marcada: bool = False, parent=None):
        super().__init__(texto, parent)
        self.setChecked(marcada)
        self.setCursor(Qt.PointingHandCursor)


class Campo(QWidget):
    """Rótulo + controle + dica/erro, empilhados."""

    def __init__(self, rotulo: str, controle: QWidget, dica: str = "", parent=None):
        super().__init__(parent)
        self.controle = controle
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ESPACO["xs"] + 2)
        layout.addWidget(Texto(rotulo, "rotulo"))
        layout.addWidget(controle)
        self._dica = dica
        self._rodape = Texto(dica, "dica")
        self._rodape.setVisible(bool(dica))
        layout.addWidget(self._rodape)
        layout.addStretch(1)  # mantém campos vizinhos alinhados pelo topo

    def definir_erro(self, mensagem: str | None):
        """Marca o campo como inválido (borda vermelha + mensagem); None limpa."""
        self.controle.setProperty("erro", bool(mensagem))
        repolir(self.controle)
        self._rodape.setProperty("papel", "erro" if mensagem else "dica")
        self._rodape.setText(mensagem or self._dica)
        self._rodape.setVisible(bool(mensagem or self._dica))
        repolir(self._rodape)


class AreaLog(QPlainTextEdit):
    """Registro somente leitura em fonte monoespaçada; `escrever` acrescenta e rola até o fim."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setProperty("papel", "log")
        self.setMinimumHeight(TAMANHOS["area_texto_min"])

    def escrever(self, texto: str):
        self.appendPlainText(texto)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class BarraProgresso(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(TAMANHOS["progresso"])


# ---------------------------------------------------------------- contêineres

class Cartao(QFrame):
    """Cartão com título/subtítulo opcionais. Conteúdo vai em `self.corpo`."""

    def __init__(self, titulo: str = "", subtitulo: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Cartao")
        p = TAMANHOS["cartao_padding"]
        externo = QVBoxLayout(self)
        externo.setContentsMargins(p, p, p, p)
        externo.setSpacing(ESPACO["lg"])
        self._acoes = QHBoxLayout()
        self._acoes.setSpacing(ESPACO["sm"])
        self._subtitulo = Texto(subtitulo, "suave")
        self._subtitulo.setWordWrap(True)
        self._subtitulo.setVisible(bool(subtitulo))
        if titulo or subtitulo:
            topo = QHBoxLayout()
            textos = QVBoxLayout()
            textos.setSpacing(2)
            if titulo:
                textos.addWidget(Texto(titulo, "subtitulo"))
            textos.addWidget(self._subtitulo)
            topo.addLayout(textos, 1)
            topo.addLayout(self._acoes)
            externo.addLayout(topo)
        self.corpo = QVBoxLayout()
        self.corpo.setSpacing(ESPACO["lg"])
        externo.addLayout(self.corpo)

    def adicionar_acao(self, widget: QWidget):
        """Coloca um widget no canto direito do título."""
        self._acoes.addWidget(widget)

    def definir_subtitulo(self, texto: str):
        self._subtitulo.setText(texto)
        self._subtitulo.setVisible(bool(texto))


class CartaoIndicador(Cartao):
    """Cartão-resumo: ícone colorido + título + valor. tom: primaria, sucesso, perigo, neutro."""

    _COR = {"primaria": "primaria", "sucesso": "sucesso", "perigo": "perigo", "neutro": "texto_suave"}

    def __init__(self, titulo: str, valor: str, icone: str, tom: str = "primaria", parent=None):
        super().__init__(parent=parent)
        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["lg"])
        self._icone, self._tom = icone, tom
        self._caixa = QLabel()
        self._caixa.setObjectName("IconeIndicador")
        self._caixa.setProperty("tom", tom)
        self._caixa.setFixedSize(44, 44)
        self._caixa.setAlignment(Qt.AlignCenter)
        linha.addWidget(self._caixa)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(Texto(titulo, "suave"))
        self._valor = Texto(valor, "valor")
        textos.addWidget(self._valor)
        linha.addLayout(textos, 1)
        self.corpo.addLayout(linha)
        tema.mudou.connect(self._pintar_icone)
        self._pintar_icone()

    def definir_valor(self, valor: str):
        self._valor.setText(valor)

    def _pintar_icone(self, *_):
        cor = tema.tokens()[self._COR[self._tom]]
        self._caixa.setPixmap(icons.pixmap(self._icone, cor, TAMANHOS["icone_lg"]))


class GradeResponsiva(QWidget):
    """Distribui widgets em colunas conforme a largura disponível (mínimo `largura_min` cada)."""

    def __init__(self, largura_min: int = 220, parent=None):
        super().__init__(parent)
        self._largura_min = largura_min
        self._itens: list[QWidget] = []
        self._colunas = 0
        self._grade = QGridLayout(self)
        self._grade.setContentsMargins(0, 0, 0, 0)
        self._grade.setSpacing(ESPACO["lg"])

    def adicionar(self, widget: QWidget):
        self._itens.append(widget)
        self._colunas = 0
        self._reorganizar()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self._reorganizar()

    def _reorganizar(self):
        espaco = self._grade.spacing()
        total = len(self._itens)
        colunas = max(1, min(total, (self.width() + espaco) // (self._largura_min + espaco)))
        while total % colunas and colunas > 1:  # prefere linhas completas (4 itens: 4 ou 2+2, nunca 3+1)
            colunas -= 1
        if colunas == self._colunas:
            return
        self._colunas = colunas
        for w in self._itens:
            self._grade.removeWidget(w)
        for i, w in enumerate(self._itens):
            self._grade.addWidget(w, i // colunas, i % colunas)
        for c in range(len(self._itens)):
            self._grade.setColumnStretch(c, 1 if c < colunas else 0)


class Pagina(QScrollArea):
    """Área de conteúdo rolável com margens padrão. Adicione itens em `self.conteudo`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        interno = QWidget()
        interno.setObjectName("Conteudo")
        interno.setAttribute(Qt.WA_StyledBackground, True)
        self.conteudo = QVBoxLayout(interno)
        m = ESPACO["xl"]
        self.conteudo.setContentsMargins(m, m, m, m)
        self.conteudo.setSpacing(ESPACO["xl"])
        self.setWidget(interno)


# ---------------------------------------------------------------- navegação

class ItemNavegacao(QPushButton):
    def __init__(self, texto: str, icone: str, parent=None):
        super().__init__(texto, parent)
        self.setProperty("nav", True)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(TAMANHOS["botao_md"])
        self.setIconSize(QSize(TAMANHOS["icone"], TAMANHOS["icone"]))
        self._icone = icone
        self.toggled.connect(self._pintar_icone)
        tema.mudou.connect(self._pintar_icone)
        self._pintar_icone()

    def _pintar_icone(self, *_):
        cores = tema.tokens()
        cor = cores["primaria"] if self.isChecked() else cores["texto_suave"]
        self.setIcon(icons.icone(self._icone, cor, TAMANHOS["icone"]))


class BarraLateral(QFrame):
    navegou = Signal(str)

    def __init__(self, nome_app: str, icone_app: str = "caminhao", parent=None):
        super().__init__(parent)
        self.setObjectName("BarraLateral")
        self.setFixedWidth(TAMANHOS["barra_lateral"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(ESPACO["md"], 0, ESPACO["md"], ESPACO["lg"])
        layout.setSpacing(ESPACO["xs"])

        marca = QHBoxLayout()
        marca.setContentsMargins(ESPACO["sm"], 0, 0, 0)
        marca.setSpacing(ESPACO["sm"])
        self._logo = QLabel()
        marca.addWidget(self._logo)
        marca.addWidget(Texto(nome_app, "marca"), 1)
        topo = QWidget()
        topo.setFixedHeight(TAMANHOS["cabecalho"])
        topo.setLayout(marca)
        layout.addWidget(topo)
        layout.addSpacing(ESPACO["sm"])

        self._itens_layout = QVBoxLayout()
        self._itens_layout.setSpacing(ESPACO["xs"])
        layout.addLayout(self._itens_layout)
        layout.addStretch(1)
        self._rodape = QVBoxLayout()
        layout.addLayout(self._rodape)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._itens: dict[str, ItemNavegacao] = {}
        self._icone_app = icone_app
        tema.mudou.connect(self._pintar_logo)
        self._pintar_logo()

    def adicionar_item(self, chave: str, texto: str, icone: str):
        item = ItemNavegacao(texto, icone)
        item.clicked.connect(lambda: self.navegou.emit(chave))
        self._grupo.addButton(item)
        self._itens_layout.addWidget(item)
        self._itens[chave] = item
        if len(self._itens) == 1:
            item.setChecked(True)

    def selecionar(self, chave: str):
        self._itens[chave].setChecked(True)
        self.navegou.emit(chave)

    def adicionar_rodape(self, widget: QWidget):
        self._rodape.addWidget(widget)

    def _pintar_logo(self, *_):
        self._logo.setPixmap(icons.pixmap(self._icone_app, tema.tokens()["primaria"], TAMANHOS["icone_lg"] + 4))


class Cabecalho(QFrame):
    def __init__(self, titulo: str = "", subtitulo: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Cabecalho")
        self.setFixedHeight(TAMANHOS["cabecalho"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(ESPACO["xl"], 0, ESPACO["xl"], 0)
        layout.setSpacing(ESPACO["md"])
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addStretch(1)
        self._titulo = Texto(titulo, "subtitulo")
        self._subtitulo = Texto(subtitulo, "dica")
        self._subtitulo.setVisible(bool(subtitulo))
        textos.addWidget(self._titulo)
        textos.addWidget(self._subtitulo)
        textos.addStretch(1)
        layout.addLayout(textos, 1)
        self._direita = QHBoxLayout()
        self._direita.setSpacing(ESPACO["sm"])
        layout.addLayout(self._direita)

    def definir_titulo(self, titulo: str, subtitulo: str = ""):
        self._titulo.setText(titulo)
        self._subtitulo.setText(subtitulo)
        self._subtitulo.setVisible(bool(subtitulo))

    def adicionar(self, widget: QWidget):
        self._direita.addWidget(widget)


# ---------------------------------------------------------------- modal

class Modal(QDialog):
    """Janela modal padrão: título, descrição, corpo livre (`self.corpo`) e rodapé com botões."""

    # tom -> (ícone, cor) mostrados ao lado do título
    _TONS = {"info": ("info", "primaria"), "sucesso": ("check", "sucesso"), "perigo": ("alerta", "perigo")}

    def __init__(self, titulo: str, descricao: str = "", parent=None, tom: str | None = None):
        super().__init__(parent)
        self.setObjectName("Modal")
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setFixedWidth(TAMANHOS["modal"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        conteudo = QVBoxLayout()
        m = ESPACO["xl"]
        conteudo.setContentsMargins(m, m, m, m)
        conteudo.setSpacing(ESPACO["sm"])
        linha_titulo = QHBoxLayout()
        linha_titulo.setSpacing(ESPACO["md"])
        if tom in self._TONS:
            nome_icone, token = self._TONS[tom]
            icone = QLabel()
            icone.setPixmap(icons.pixmap(nome_icone, tema.tokens()[token], TAMANHOS["icone_lg"] + 2))
            linha_titulo.addWidget(icone)
        linha_titulo.addWidget(Texto(titulo, "subtitulo"), 1)
        conteudo.addLayout(linha_titulo)
        if descricao:
            texto = Texto(descricao, "suave")
            texto.setWordWrap(True)
            conteudo.addWidget(texto)
        self.corpo = QVBoxLayout()
        self.corpo.setSpacing(ESPACO["lg"])
        conteudo.addLayout(self.corpo)
        layout.addLayout(conteudo)

        rodape = QFrame()
        rodape.setObjectName("ModalRodape")
        self._botoes = QHBoxLayout(rodape)
        self._botoes.setContentsMargins(m, ESPACO["lg"], m, ESPACO["lg"])
        self._botoes.setSpacing(ESPACO["sm"])
        self._botoes.addStretch(1)
        layout.addWidget(rodape)

    def showEvent(self, evento):
        # altura exata para a largura fixa (o Qt superestima quando há texto com quebra de linha)
        altura = self.layout().heightForWidth(self.width())
        if altura > 0:
            self.setFixedHeight(altura)
        super().showEvent(evento)

    def adicionar_botao(self, botao: QPushButton) -> QPushButton:
        self._botoes.addWidget(botao)
        return botao

    @classmethod
    def escolher(cls, parent, titulo: str, descricao: str, opcoes: list, tom: str | None = None):
        """Mostra botões (rótulo, variante, valor) e devolve o valor clicado; None se fechar a janela.
        O último botão é o padrão (Enter)."""
        dialogo = cls(titulo, descricao, parent, tom)
        escolha = {}
        for rotulo, variante, valor in opcoes:
            botao = dialogo.adicionar_botao(Botao(rotulo, variante))
            botao.clicked.connect(lambda _=False, v=valor: (escolha.update(valor=v), dialogo.accept()))
        botao.setDefault(True)
        botao.setFocus()
        dialogo.exec()
        return escolha.get("valor")

    @classmethod
    def confirmar(cls, parent, titulo: str, descricao: str, texto_ok: str = "Confirmar",
                  destrutivo: bool = False, tom: str | None = None) -> bool:
        return bool(cls.escolher(parent, titulo, descricao, [
            ("Cancelar", "secundario", False),
            (texto_ok, "perigo" if destrutivo else "primario", True)], tom))

    @classmethod
    def informar(cls, parent, titulo: str, descricao: str, tom: str = "info"):
        cls.escolher(parent, titulo, descricao, [("OK", "primario", True)], tom)


# ---------------------------------------------------------------- tabela

class Tabela(QTableWidget):
    """Tabela somente leitura com linhas de 44px. Valores podem ser texto ou widget (ex.: Etiqueta)."""

    def __init__(self, colunas: list[str], alinhar_direita=(), coluna_flexivel: int = 0, parent=None):
        super().__init__(0, len(colunas), parent)
        self._direita = set(alinhar_direita)
        self.setHorizontalHeaderLabels(colunas)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(TAMANHOS["linha_tabela"])
        cab = self.horizontalHeader()
        cab.setFixedHeight(TAMANHOS["cabecalho_tabela"])
        cab.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # a coluna flexível ocupa o espaço livre; as demais se ajustam ao conteúdo
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(coluna_flexivel, QHeaderView.Stretch)
        cab.setMinimumSectionSize(100)
        cab.setHighlightSections(False)
        self.setWordWrap(False)
        for c in self._direita:
            self.horizontalHeaderItem(c).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setShowGrid(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setFrameShape(QFrame.NoFrame)
        self.setMouseTracking(True)  # hover nas linhas

    def adicionar_linha(self, valores: list) -> int:
        linha = self.rowCount()
        self.insertRow(linha)
        for coluna, valor in enumerate(valores):
            self.definir_celula(linha, coluna, valor)
        return linha

    def definir_celula(self, linha: int, coluna: int, valor) -> QTableWidgetItem:
        """Texto vira item comum; widget (ex.: Etiqueta) fica sobre um item sem texto."""
        if isinstance(valor, QWidget):
            valor.ensurePolished()  # tamanho já com o padding do QSS
            envoltorio = QWidget()
            caixa = QHBoxLayout(envoltorio)
            caixa.setContentsMargins(0, 0, 0, 0)  # o padding do item (QSS) já dá o recuo
            caixa.addWidget(valor)
            caixa.addStretch(1)
            self.setCellWidget(linha, coluna, envoltorio)
            item = QTableWidgetItem()  # guarda o texto só para o filtro
            item.setData(Qt.UserRole, valor.property("text") or "")
        else:
            self.removeCellWidget(linha, coluna)
            item = QTableWidgetItem(str(valor))
            alinhamento = Qt.AlignRight if coluna in self._direita else Qt.AlignLeft
            item.setTextAlignment(alinhamento | Qt.AlignVCenter)
        self.setItem(linha, coluna, item)
        return item

    def sizeHintForColumn(self, coluna: int) -> int:
        """Considera também os widgets das células (o Qt só mede o texto)."""
        largura = super().sizeHintForColumn(coluna)
        for linha in range(self.rowCount()):
            widget = self.cellWidget(linha, coluna)
            if widget:
                largura = max(largura, widget.sizeHint().width() + 2 * ESPACO["md"])  # + padding do item
        return largura

    def filtrar(self, termo: str):
        """Esconde as linhas que não contêm o termo em nenhuma coluna."""
        termo = termo.strip().lower()
        for linha in range(self.rowCount()):
            itens = (self.item(linha, c) for c in range(self.columnCount()))
            textos = [(i.text() or i.data(Qt.UserRole) or "").lower() for i in itens if i]
            self.setRowHidden(linha, bool(termo) and not any(termo in t for t in textos))
