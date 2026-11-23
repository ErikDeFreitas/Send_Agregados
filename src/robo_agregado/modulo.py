"""MODULO do RoboAgregado para a casca e o avulso. Leve: só dados e a fábrica (sem pandas, sem criar pastas)."""

from tcm_ui.modulo import Contexto, Modulo, Pagina

from robo_agregado import __version__, dados


def criar(contexto: Contexto):
    from robo_agregado.instancia import RoboAgregado  # import pesado só quando o módulo é aberto
    return RoboAgregado(contexto)


MODULO = Modulo(
    id="robo_agregado",
    nome="RoboAgregado",
    icone="caminhao",
    versao=__version__,
    grupo_ad="SF-RoboAgregado",
    repositorio="ErikDeFreitas/Send_Agregados",
    nome_exe="RoboAgregado.exe",
    pasta_dados=dados.PASTA,
    paginas=(Pagina("extrato", "Extrato de fretes", "Envio dos extratos semanais aos agregados", "enviar"),),
    criar=criar,
)
