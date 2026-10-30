"""Ícones SVG do Design System (traço, 24x24), coloridos na hora conforme o tema."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONES = {
    "painel": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/>'
              '<rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "componentes": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/>',
    "config": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/>'
              '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "enviar": '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
    "usuarios": '<circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/>'
                '<path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M21 21v-2a4 4 0 0 0-3-3.85"/>',
    "arquivo": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "pasta": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "chave": '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.8-9.8M17 6l3 3M14 9l2 2"/>',
    "olho": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "parar": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "pesquisa": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "sol": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41'
           'M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "lua": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "seta": '<path d="m6 9 6 6 6-6"/>',
    "fechar": '<path d="M18 6 6 18M6 6l12 12"/>',
    "alerta": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
              '<path d="M12 9v4M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "caminhao": '<path d="M1 4h14v12H1z"/><path d="M15 8h4l3 3v5h-7z"/>'
                '<circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
}

_MOLDE = ('<svg xmlns="http://www.w3.org/2000/svg" width="{t}" height="{t}" viewBox="0 0 24 24" fill="none" '
          'stroke="{cor}" stroke-width="{e}" stroke-linecap="round" stroke-linejoin="round">{corpo}</svg>')

_PASTA_TEMP = Path(tempfile.gettempdir()) / "roboagregado_ds"


def svg(nome: str, cor: str, tamanho: int = 24, espessura: float = 2) -> str:
    return _MOLDE.format(t=tamanho, cor=cor, e=espessura, corpo=ICONES[nome])


def pixmap(nome: str, cor: str, tamanho: int = 18, escala: int = 2) -> QPixmap:
    """Desenha o ícone em alta resolução (escala) para ficar nítido em telas com zoom."""
    renderizador = QSvgRenderer(QByteArray(svg(nome, cor).encode()))
    imagem = QPixmap(tamanho * escala, tamanho * escala)
    imagem.fill(Qt.transparent)
    pintor = QPainter(imagem)
    renderizador.render(pintor)
    pintor.end()
    imagem.setDevicePixelRatio(escala)
    return imagem


def icone(nome: str, cor: str, tamanho: int = 18, cor_desab: str | None = None) -> QIcon:
    resultado = QIcon(pixmap(nome, cor, tamanho))
    if cor_desab:
        resultado.addPixmap(pixmap(nome, cor_desab, tamanho), QIcon.Disabled)
    return resultado


def arquivo(nome: str, cor: str, tamanho: int, espessura: float = 2) -> str:
    """Grava o SVG em disco para uso em url(...) no QSS e devolve o caminho."""
    _PASTA_TEMP.mkdir(parents=True, exist_ok=True)
    destino = _PASTA_TEMP / f"{nome}_{cor.lstrip('#')}_{tamanho}.svg"
    if not destino.exists():
        destino.write_text(svg(nome, cor, tamanho, espessura), encoding="utf-8")
    return destino.as_posix()
