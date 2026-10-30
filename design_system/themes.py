"""Tokens do Design System (cores, tamanhos, espaçamentos) e gerenciamento dos temas claro/escuro."""
import re
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from . import icons

# Cores de identidade: iguais nos dois temas.
MARCA = {
    "primaria": "#2563EB", "primaria_hover": "#1D4ED8", "primaria_press": "#1E40AF",
    "perigo": "#DC2626", "perigo_hover": "#B91C1C", "perigo_press": "#991B1B",
    "sucesso": "#16A34A",
    "branco": "#FFFFFF",
}

# Cores neutras: mudam conforme o tema.
# "conteudo" é o fundo da área de trabalho; "barra" é o fundo da barra lateral e do cabeçalho.
TEMAS = {
    "claro": {
        "fundo": "#FFFFFF", "fundo_secundario": "#F9FAFB", "cartao": "#FFFFFF",
        "conteudo": "#F9FAFB", "barra": "#FFFFFF",
        "texto": "#111827", "texto_suave": "#6B7280",
        "borda": "#E5E7EB", "borda_forte": "#D1D5DB",
        "hover": "#F3F4F6", "pressionado": "#E5E7EB", "campo_fundo": "#FFFFFF",
        "desab_fundo": "#F3F4F6", "desab_texto": "#9CA3AF",
        "primaria_suave": "#EFF6FF", "primaria_desab": "#93C5FD", "selecao": "#DBEAFE",
        "perigo_suave": "#FEF2F2", "perigo_desab": "#FCA5A5",
        "sucesso_suave": "#F0FDF4", "neutro_suave": "#F3F4F6",
        "rolagem": "#D1D5DB", "dica_fundo": "#111827", "dica_texto": "#F9FAFB",
    },
    "escuro": {
        "fundo": "#111827", "fundo_secundario": "#1F2937", "cartao": "#1F2937",
        "conteudo": "#111827", "barra": "#1F2937",
        "texto": "#F9FAFB", "texto_suave": "#9CA3AF",
        "borda": "#374151", "borda_forte": "#4B5563",
        "hover": "#374151", "pressionado": "#4B5563", "campo_fundo": "#111827",
        "desab_fundo": "#374151", "desab_texto": "#6B7280",
        "primaria_suave": "rgba(37, 99, 235, 0.20)", "primaria_desab": "#1E3A8A", "selecao": "#1E3A5F",
        "perigo_suave": "rgba(220, 38, 38, 0.18)", "perigo_desab": "#7F1D1D",
        "sucesso_suave": "rgba(22, 163, 74, 0.18)", "neutro_suave": "#374151",
        "rolagem": "#4B5563", "dica_fundo": "#F9FAFB", "dica_texto": "#111827",
    },
}

# Dimensões em pixels.
TAMANHOS = {
    "botao_sm": 32, "botao_md": 40, "botao_lg": 48,
    "campo": 42, "area_texto_min": 100, "check": 18,
    "barra_lateral": 240, "cabecalho": 64, "modal": 480,
    "cartao_padding": 20, "linha_tabela": 44, "cabecalho_tabela": 40,
    "icone": 18, "icone_lg": 20, "progresso": 8, "etiqueta_altura": 22, "etiqueta_padding": 10,
    "raio": 8, "raio_cartao": 12, "raio_pequeno": 4,
    "fonte": 13, "fonte_rotulo": 12, "fonte_subtitulo": 15, "fonte_marca": 16,
    "fonte_titulo": 22, "fonte_valor": 24,
}

ESPACO = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}

FONTES = ("Inter", "Segoe UI")  # a primeira instalada; se nenhuma existir, fica a do sistema

_ARQUIVO_QSS = Path(__file__).with_name("styles.qss")
_TOKEN = re.compile(r"@([a-z0-9_]+)")


class GerenciadorTema(QObject):
    """Guarda o tema atual, aplica no QApplication e avisa os componentes pelo sinal `mudou`."""

    mudou = Signal(str)

    def __init__(self):
        super().__init__()
        self._config = QSettings("TCM", "RoboAgregado")
        nome = self._config.value("aparencia/tema", "claro")
        self._nome = nome if nome in TEMAS else "claro"

    @property
    def nome(self) -> str:
        return self._nome

    @property
    def escuro(self) -> bool:
        return self._nome == "escuro"

    def tokens(self) -> dict:
        return {**MARCA, **TEMAS[self._nome]}

    def definir(self, nome: str):
        if nome not in TEMAS:
            raise ValueError(f"Tema desconhecido: {nome}")
        if nome == self._nome:
            return
        self._nome = nome
        self._config.setValue("aparencia/tema", nome)
        self.aplicar()
        self.mudou.emit(nome)

    def alternar(self):
        self.definir("claro" if self.escuro else "escuro")

    def aplicar(self, app: QApplication | None = None):
        app = app or QApplication.instance()
        cores = self.tokens()
        if app.style().name().lower() != "fusion":
            app.setStyle("Fusion")  # mesmo desenho no Windows e no macOS
        app.setFont(_fonte())
        app.setPalette(_paleta(cores))
        app.setStyleSheet(self._qss(cores))
        try:  # barra de título nativa acompanha o tema (Qt 6.8+)
            QGuiApplication.styleHints().setColorScheme(
                Qt.ColorScheme.Dark if self.escuro else Qt.ColorScheme.Light)
        except AttributeError:
            pass

    def _qss(self, cores: dict) -> str:
        valores = {
            **cores,
            **{chave: f"{valor}px" for chave, valor in TAMANHOS.items()},
            "icone_check": icons.arquivo("check", MARCA["branco"], 12, espessura=3),
            "icone_seta": icons.arquivo("seta", cores["texto_suave"], 16),
        }
        modelo = _ARQUIVO_QSS.read_text(encoding="utf-8")
        return _TOKEN.sub(lambda m: valores[m.group(1)], modelo)


def _fonte() -> QFont:
    instaladas = set(QFontDatabase.families())
    fonte = QFont()
    for familia in FONTES:
        if familia in instaladas:
            fonte = QFont(familia)
            break
    fonte.setPixelSize(TAMANHOS["fonte"])
    return fonte


def _paleta(cores: dict) -> QPalette:
    """Paleta para o que o QSS não alcança (placeholder, diálogos nativos, dicas)."""
    p = QPalette()
    pares = {
        QPalette.Window: "conteudo", QPalette.WindowText: "texto",
        QPalette.Base: "campo_fundo", QPalette.AlternateBase: "fundo_secundario",
        QPalette.Text: "texto", QPalette.Button: "cartao", QPalette.ButtonText: "texto",
        QPalette.Highlight: "primaria", QPalette.HighlightedText: "branco",
        QPalette.PlaceholderText: "texto_suave", QPalette.Link: "primaria",
        QPalette.ToolTipBase: "dica_fundo", QPalette.ToolTipText: "dica_texto",
    }
    for papel, token in pares.items():
        p.setColor(papel, QColor(cores[token]))
    for papel in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, papel, QColor(cores["desab_texto"]))
    return p


tema = GerenciadorTema()
