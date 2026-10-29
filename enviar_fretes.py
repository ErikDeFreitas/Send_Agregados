"""
Envia a cada agregado um e-mail com apenas os seus fretes, a partir da planilha.

Este arquivo contém o núcleo do sistema (usado pelo app.py) e também funciona por linha de comando:
    python enviar_fretes.py --planilha "C:\\...\\Modelo.xlsx" --listar
    python enviar_fretes.py --cnpj 12.345.678/0001-90      # pré-visualiza (não envia)
    python enviar_fretes.py --cnpj 12345678000190 --enviar # envia para um agregado
    python enviar_fretes.py --todos --enviar               # envia para todos
"""

import argparse
import configparser
import csv
import hashlib
import html
import os
import re
import shutil
import smtplib
import ssl
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

import pandas as pd

# no executável, config, .env e log ficam numa pasta própria (não soltos ao lado do .exe)
NOME_PASTA_DADOS = "RoboAgregado"
if getattr(sys, "frozen", False):
    PASTA = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / NOME_PASTA_DADOS
    PASTA.mkdir(parents=True, exist_ok=True)
    # versões antigas gravavam estes arquivos ao lado do .exe: leva para a pasta nova
    for _nome in (".env", "log_envios.csv", "preferencias.json"):
        _antigo = Path(sys.executable).resolve().parent / _nome
        if _antigo.is_file() and not (PASTA / _nome).exists():
            try:
                shutil.move(str(_antigo), str(PASTA / _nome))
            except OSError:
                pass
else:
    PASTA = Path(__file__).resolve().parent
PASTA_PREVIA = PASTA / "previas"
ARQUIVO_LOG = PASTA / "log_envios.csv"
ARQUIVO_CONFIG = PASTA / "config.ini"
ARQUIVO_ENV = PASTA / ".env"
ESPERA_RECUSAS = 20  # segundos aguardando avisos de não entrega após o envio (só Outlook)
CABECALHO_LOG = ["data_hora", "cnpj_cpf", "nome", "email", "assunto", "status", "chave"]
RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


class ErroPlanilha(Exception):
    pass


class ErroEnvio(Exception):
    """Erro de envio com mensagem segura para exibir e registrar (sem credenciais)."""


class ErroFatal(ErroEnvio):
    """Erro que afeta o lote inteiro (conexão, login, remetente): não adianta continuar."""


# ------------------------------------------------------------------ utilidades

def lista(valor: str) -> list[str]:
    return [v.strip() for v in valor.split(",") if v.strip()]


def chave_coluna(nome) -> str:
    """'Nº Referência ' e 'N° referencia' viram a mesma chave: 'nreferencia'."""
    sem_acento = unicodedata.normalize("NFD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def alinhar_colunas(df: pd.DataFrame, nomes_config) -> pd.DataFrame:
    """Renomeia os cabeçalhos da planilha para a grafia usada no config.ini."""
    por_chave = {chave_coluna(c): c for c in df.columns}
    renomear = {}
    for nome in filter(None, nomes_config):
        original = por_chave.get(chave_coluna(nome))
        if original is not None and original != nome:
            renomear[original] = nome
    return df.rename(columns=renomear)


def normalizar_documento(valor) -> str:
    """Deixa só os dígitos e recupera zeros à esquerda perdidos pelo Excel."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    digitos = re.sub(r"\D", "", str(valor))
    if not digitos:
        return ""
    return digitos.zfill(11) if len(digitos) <= 11 else digitos.zfill(14)


def formatar_documento(doc: str) -> str:
    if len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    if len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    return doc


def formatar_moeda(valor) -> str:
    if pd.isna(valor):
        return ""
    texto = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_data(valor) -> str:
    if pd.isna(valor):
        return ""
    data = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    return data.strftime("%d/%m/%Y") if not pd.isna(data) else str(valor)


def para_numero(serie: pd.Series) -> pd.Series:
    """Converte valores como 'R$ 1.234,56' ou 1234.56 em número."""
    def conv(v):
        if pd.isna(v) or isinstance(v, (int, float)):
            return v
        t = re.sub(r"[^\d,.\-]", "", str(v))
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        try:
            return float(t)
        except ValueError:
            return None
    return serie.map(conv)


def extrair_semana(textos) -> str:
    """'VW SEMANA 42 - VCTO 04-11-2026' -> 'Semana 42'; várias -> 'Semanas 40, 41 e 42'."""
    numeros = sorted({int(n) for t in textos for n in re.findall(r"semana\s*(\d+)", str(t), re.I)})
    if not numeros:
        return " / ".join(textos)
    if len(numeros) == 1:
        return f"Semana {numeros[0]}"
    nums = [str(n) for n in numeros]
    return f"Semanas {', '.join(nums[:-1])} e {nums[-1]}"


def separar_emails(texto: str) -> list[str]:
    return [e.strip() for e in re.split(r"[;,]", texto or "") if e.strip()]


def emails_invalidos(texto: str) -> list[str]:
    return [e for e in separar_emails(texto) if not RE_EMAIL.match(e)]


def mascarar_documento(doc: str) -> str:
    """Log sem o documento completo: 123.***.***-10 / 12.***.***/0001-90."""
    f = formatar_documento(doc)
    if len(doc) == 11:
        return f"{f[:3]}.***.***-{f[-2:]}"
    if len(doc) == 14:
        return f"{f[:2]}.***.***/{f[-7:]}"
    return "***"


def chave_envio(doc: str, assunto: str) -> str:
    """Identifica 'este extrato para este agregado' sem guardar o documento em claro."""
    return hashlib.sha256(f"{doc}|{assunto}".encode("utf-8")).hexdigest()[:16]


def limpar_cabecalho(texto: str) -> str:
    """Remove quebras de linha que poderiam injetar cabeçalhos no e-mail."""
    return re.sub(r"[\r\n]+", " ", str(texto)).strip()


# ------------------------------------------------------------------ config e planilha

def carregar_env(caminho=None):
    """Lê o .env (CHAVE=valor) para as variáveis de ambiente, sem sobrescrever as existentes."""
    caminho = Path(caminho or ARQUIVO_ENV)
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        os.environ.setdefault(chave.strip(), valor)


def credenciais_ok() -> bool:
    return bool(os.environ.get("SMTP_USUARIO") and os.environ.get("SMTP_SENHA"))


def cco_padrao(cfg) -> str:
    """CCO padrão: informado na janela de credenciais (.env); o config.ini só serve de reserva."""
    return (os.environ.get("EMAIL_CCO") or os.environ.get("EMAIL_CC")
            or cfg["email"].get("cco", "") or cfg["email"].get("cc", ""))


def salvar_env(usuario: str, senha: str, cco: str = ""):
    """Grava remetente, senha e CCO padrão no .env (acesso restrito ao usuário do Windows)."""
    ARQUIVO_ENV.write_text(
        f'SMTP_USUARIO="{usuario}"\nSMTP_SENHA="{senha}"\nEMAIL_CCO="{cco}"\n', encoding="utf-8")
    try:  # remove as permissões herdadas: só o usuário atual lê o arquivo
        subprocess.run(["icacls", str(ARQUIVO_ENV), "/inheritance:r", "/grant:r",
                        f"{os.environ.get('USERNAME', '')}:F"],
                       capture_output=True, timeout=15, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError):
        pass
    os.environ["SMTP_USUARIO"], os.environ["SMTP_SENHA"], os.environ["EMAIL_CCO"] = usuario, senha, cco
    os.environ.pop("EMAIL_CC", None)


def conectar_smtp(cfg, usuario: str, senha: str):
    """Abre conexão segura (STARTTLS com certificado verificado) e autentica."""
    s = cfg["smtp"]
    try:
        conexao = smtplib.SMTP(s.get("servidor", "smtp.office365.com"), s.getint("porta", 587),
                               timeout=30)
        conexao.ehlo()
        conexao.starttls(context=ssl.create_default_context())
        conexao.ehlo()
        conexao.login(usuario, senha)
        return conexao
    except smtplib.SMTPAuthenticationError:
        raise ErroFatal("Falha de autenticação no SMTP: usuário/senha incorretos ou envio SMTP "
                        "desabilitado para a conta.") from None
    except ssl.SSLError:
        raise ErroFatal("Falha na conexão segura (TLS) com o servidor SMTP.") from None
    except (OSError, smtplib.SMTPException) as e:
        raise ErroFatal(f"Não foi possível conectar ao servidor SMTP ({type(e).__name__}).") from None


def testar_login(cfg, usuario: str, senha: str):
    """Valida usuário e senha no servidor, sem enviar nenhuma mensagem."""
    conexao = conectar_smtp(cfg, usuario, senha)
    try:
        conexao.quit()
    except Exception:
        pass


def carregar_config(caminho=None) -> configparser.ConfigParser:
    caminho = Path(caminho or ARQUIVO_CONFIG)
    if not caminho.exists() and getattr(sys, "frozen", False):
        # primeira execução do .exe: cria o config.ini padrão ao lado do executável
        shutil.copy(Path(sys._MEIPASS) / "config.ini", caminho)
    carregar_env()
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(caminho, encoding="utf-8")
    return cfg


def _ler_aba(arquivo, aba_desejada, ignorar=()):
    """Lê a aba pelo nome; se não existir, usa a primeira aba que não esteja em `ignorar`."""
    abas = pd.ExcelFile(arquivo).sheet_names
    por_chave = {chave_coluna(a): a for a in abas}
    aba = por_chave.get(chave_coluna(aba_desejada)) if aba_desejada else None
    if aba is None:
        restantes = [a for a in abas if chave_coluna(a) not in {chave_coluna(i) for i in ignorar}]
        if not restantes:
            raise ErroPlanilha(f"Nenhuma aba de fretes encontrada. Abas: {abas}")
        aba = restantes[0]
    df = pd.read_excel(arquivo, sheet_name=aba, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def carregar_dados(cfg, arquivo=None):
    p = cfg["planilha"]
    c = cfg["cadastro"]
    arquivo = Path(arquivo or p.get("arquivo", ""))
    if not arquivo.is_absolute():
        arquivo = PASTA / arquivo
    if not arquivo.is_file():
        raise ErroPlanilha(f"Planilha não encontrada: {arquivo}")

    df = _ler_aba(arquivo, p.get("aba"), ignorar=[c.get("aba", "")])
    df = alinhar_colunas(df, [p["coluna_documento"], p["coluna_nome"], p.get("coluna_email", ""),
                              p.get("coluna_periodo", "")]
                         + lista(p.get("colunas_exibidas", "")) + lista(p.get("colunas_moeda", ""))
                         + lista(p.get("colunas_data", "")))

    obrigatorias = [p["coluna_documento"], p["coluna_nome"]]
    faltando = [col for col in obrigatorias if col not in df.columns]
    if faltando:
        raise ErroPlanilha(f"Colunas não encontradas na planilha: {faltando}\n"
                           f"Colunas existentes: {list(df.columns)}")

    df["_doc"] = df[p["coluna_documento"]].map(normalizar_documento)
    df = df[df["_doc"] != ""]

    for col in lista(p.get("colunas_moeda", "")):
        if col in df.columns:
            df[col] = para_numero(df[col])

    # e-mails: aba de cadastro separada ou coluna na própria aba
    emails = {}
    if c.get("aba"):
        try:
            cad = pd.read_excel(arquivo, sheet_name=c["aba"], dtype=str)
        except ValueError:
            raise ErroPlanilha(f"Aba de cadastro '{c['aba']}' não encontrada na planilha.")
        cad.columns = [str(x).strip() for x in cad.columns]
        cad = alinhar_colunas(cad, [c["coluna_documento"], c["coluna_email"]])
        for _, linha in cad.iterrows():
            doc = normalizar_documento(linha[c["coluna_documento"]])
            if doc and not pd.isna(linha[c["coluna_email"]]):
                emails[doc] = str(linha[c["coluna_email"]]).strip()
    elif p.get("coluna_email") in df.columns:
        for doc, grupo in df.groupby("_doc"):
            validos = grupo[p["coluna_email"]].dropna().astype(str).str.strip()
            validos = validos[validos != ""]
            if not validos.empty:
                emails[doc] = validos.iloc[0]

    return df, emails


# ------------------------------------------------------------------ e-mail

def montar_html(cfg, nome, doc, fretes: pd.DataFrame, periodo) -> str:
    p = cfg["planilha"]
    ignorar = {p["coluna_documento"], p["coluna_nome"], p.get("coluna_email", ""), "_doc"}
    colunas = [c for c in lista(p.get("colunas_exibidas", "")) if c in fretes.columns] \
        or [c for c in fretes.columns if c not in ignorar]
    moeda = set(lista(p.get("colunas_moeda", "")))
    datas = set(lista(p.get("colunas_data", "")))

    def celula(col, valor):
        if col in moeda:
            return formatar_moeda(valor)
        if col in datas:
            return formatar_data(valor)
        if pd.isna(valor):
            return ""
        if isinstance(valor, float) and valor.is_integer():
            return str(int(valor))  # evita "164560.0" em colunas numéricas com vazios
        return str(valor).strip()

    # estilos inline e layout em tabelas: é o que Outlook, Gmail e celulares renderizam bem
    fonte = "font-family:'Segoe UI',Arial,Helvetica,sans-serif"
    estilo_th = (f"{fonte};background:#1f4e79;color:#ffffff;padding:9px 10px;font-size:12px;"
                 "font-weight:600;text-align:left;white-space:nowrap;border-bottom:2px solid #163a5c")
    estilo_td = f"{fonte};padding:8px 10px;font-size:13px;color:#222;border-bottom:1px solid #e3e8ee"
    cab = "".join(f'<th style="{estilo_th}{";text-align:right" if c in moeda else ""}">'
                  f'{html.escape(c)}</th>' for c in colunas)

    linhas = []
    for i, (_, f) in enumerate(fretes.iterrows()):
        fundo = "#f6f9fc" if i % 2 else "#ffffff"
        tds = "".join(
            f'<td style="{estilo_td}{";text-align:right;white-space:nowrap" if c in moeda else ""}">'
            f'{html.escape(celula(c, f[c]))}</td>' for c in colunas)
        linhas.append(f'<tr style="background:{fundo}">{tds}</tr>')

    total = ""
    if any(c in moeda for c in colunas):
        tds = "".join(
            f'<td style="{estilo_td};font-weight:700;background:#e4edf6;'
            f'{"text-align:right;white-space:nowrap" if c in moeda else ""}">'
            f'{formatar_moeda(fretes[c].sum()) if c in moeda else ("TOTAL" if j == 0 else "")}</td>'
            for j, c in enumerate(colunas))
        total = f"<tr>{tds}</tr>"

    # cartões de resumo (quebram em linhas no celular)
    col_total = next((c for c in colunas if c in moeda), None)
    resumo = [("CNPJ/CPF", formatar_documento(doc)), ("Fretes", str(len(fretes)))]
    if col_total:
        resumo.append(("Total", formatar_moeda(fretes[col_total].sum())))
    cartoes = "".join(
        f'<div style="display:inline-block;min-width:140px;margin:0 8px 8px 0;padding:10px 14px;'
        f'background:#f2f6fa;border-left:3px solid #1f4e79;vertical-align:top">'
        f'<div style="{fonte};font-size:11px;color:#5b6b7b;text-transform:uppercase">{rotulo}</div>'
        f'<div style="{fonte};font-size:16px;font-weight:700;color:#1f4e79">{html.escape(valor)}</div>'
        f'</div>' for rotulo, valor in resumo)

    assinatura = html.escape(cfg["email"].get("assinatura", ""))
    texto = f"{fonte};font-size:14px;line-height:1.5;color:#222;margin:0 0 12px"
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Extrato de Fretes</title></head>
<body style="margin:0;padding:0;background:#eef2f6">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f6">
<tr><td align="center" style="padding:20px 8px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
 style="max-width:760px;background:#ffffff;border:1px solid #dbe2ea">
<tr><td style="background:#1f4e79;padding:18px 22px">
<div style="{fonte};font-size:20px;font-weight:700;color:#ffffff">Extrato de Fretes</div>
<div style="{fonte};font-size:13px;color:#d6e2ee;margin-top:4px">{html.escape(periodo)}</div>
</td></tr>
<tr><td style="padding:22px">
<p style="{texto}">Olá, <b>{html.escape(nome)}</b>,</p>
<p style="{texto}">Segue o extrato dos seus fretes referente a <b>{html.escape(periodo)}</b>.</p>
<div style="margin:4px 0 14px">{cartoes}</div>
<div style="overflow-x:auto;-webkit-overflow-scrolling:touch">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;min-width:560px">
<thead><tr>{cab}</tr></thead>
<tbody>{''.join(linhas)}{total}</tbody>
</table>
</div>
<p style="{texto};margin-top:20px">O comprovante de entrega deverá ser enviado imediatamente após a conclusão do serviço. A ausência desse documento impedirá a liberação do pagamento dos respectivos valores apresentados na prévia, que permanecerão pendentes até a devida regularização.</p>
<p style="{texto}">Este é um e-mail automático. Por favor, não responda.</p>
<p style="{texto}">Em caso de dúvidas, favor entrar em contato com seu responsável de atendimento.</p>
<p style="{texto}">Atenciosamente,<br>{assinatura}</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def preparar_envios(cfg, df, emails, docs=None, periodo_fixo="") -> list[dict]:
    """Monta, para cada CNPJ/CPF, os dados do e-mail (destinatário, assunto, corpo, total)."""
    p = cfg["planilha"]
    col_periodo = p.get("coluna_periodo", "")
    col_total = next((c for c in lista(p.get("colunas_moeda", "")) if c in df.columns), None)
    docs = sorted(df["_doc"].unique()) if docs is None else docs

    envios = []
    for doc in docs:
        fretes = df[df["_doc"] == doc]
        if fretes.empty:
            envios.append({"doc": doc, "nome": "", "email": "", "fretes": 0, "erro": "nenhum frete"})
            continue
        nome = str(fretes[p["coluna_nome"]].iloc[0]).strip()
        textos = []
        if col_periodo in fretes.columns:
            textos = list(fretes[col_periodo].dropna().astype(str).str.strip().unique())
        periodo = periodo_fixo or " / ".join(textos)
        semana = periodo_fixo or extrair_semana(textos)
        assunto = limpar_cabecalho(cfg["email"]["assunto"].format(
            nome=nome, documento=formatar_documento(doc), periodo=periodo, semana=semana))
        envios.append({
            "doc": doc,
            "nome": nome,
            "email": emails.get(doc, ""),
            "fretes": len(fretes),
            "total": fretes[col_total].sum() if col_total else None,
            "assunto": assunto,
            "corpo": montar_html(cfg, nome, doc, fretes, periodo),
        })
    return envios


def enviar_outlook(para, assunto, corpo, remetente="", cco=""):
    import win32com.client  # pywin32
    outlook = win32com.client.Dispatch("Outlook.Application")
    msg = outlook.CreateItem(0)
    msg.To = para
    if cco:
        msg.BCC = cco
    if remetente:
        msg.SentOnBehalfOfName = remetente
        # guarda a cópia em "Itens Enviados" da caixa compartilhada, se houver acesso
        try:
            ns = outlook.GetNamespace("MAPI")
            dono = ns.CreateRecipient(remetente)
            if dono.Resolve():
                msg.SaveSentMessageFolder = ns.GetSharedDefaultFolder(dono, 5)
        except Exception:
            pass
    msg.Subject = assunto
    msg.HTMLBody = corpo
    msg.Send()


def html_para_texto(corpo: str) -> str:
    """Versão em texto simples do e-mail, para leitores que não exibem HTML."""
    t = re.sub(r"(?is)<(head|style).*?</\1>", "", corpo)
    t = re.sub(r"(?i)<br\s*/?>|</(p|tr|div|h\d)>", "\n", t)
    t = re.sub(r"(?i)</t[dh]>", "\t", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+\n", "\n", t)).strip()


def remetente_padrao(cfg) -> str:
    """Remetente usado quando o campo fica vazio."""
    if cfg["email"].get("metodo", "outlook") == "outlook":
        return ""  # e-mail logado no Outlook
    return os.environ.get("SMTP_USUARIO") or cfg["smtp"].get("remetente", "")


class Enviador:
    """
    Envia os e-mails de um lote pelo método do config.ini (smtp ou outlook).
    No SMTP, abre UMA conexão segura (STARTTLS com certificado verificado) para o lote todo.
    Uso:  with Enviador(cfg) as env: env.enviar(envio, remetente, cco)
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.metodo = cfg["email"].get("metodo", "outlook").strip().lower()
        self.conexao = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    def fechar(self):
        if self.conexao is not None:
            try:
                self.conexao.quit()
            except Exception:
                pass
            self.conexao = None

    def _conectar(self):
        s = self.cfg["smtp"]
        usuario = os.environ.get("SMTP_USUARIO") or s.get("usuario", "")
        senha = os.environ.get("SMTP_SENHA", "")
        if not usuario or not senha:
            raise ErroFatal("Credenciais SMTP não informadas. Use o botão 'Credenciais...' da tela.")
        self.conexao = conectar_smtp(self.cfg, usuario, senha)

    def enviar(self, envio, remetente="", cco=""):
        para = list(dict.fromkeys(separar_emails(envio["email"])))
        ja = {e.lower() for e in para}
        oculta = [e for e in dict.fromkeys(separar_emails(cco)) if e.lower() not in ja]
        invalidos = emails_invalidos(envio["email"]) + emails_invalidos(cco)
        if not para:
            raise ErroEnvio("Destinatário sem e-mail cadastrado.")
        if invalidos:
            raise ErroEnvio(f"E-mail inválido: {', '.join(invalidos)}")
        assunto = limpar_cabecalho(envio["assunto"])

        if self.metodo == "outlook":
            try:
                enviar_outlook("; ".join(para), assunto, envio["corpo"], remetente, "; ".join(oculta))
            except Exception as e:
                raise ErroEnvio(f"Falha ao enviar pelo Outlook ({type(e).__name__}).") from None
            return

        remetente = remetente or remetente_padrao(self.cfg)
        if emails_invalidos(remetente) or not remetente:
            raise ErroFatal(f"Remetente inválido: {remetente or '(vazio)'}")
        msg = EmailMessage()
        nome_rem = limpar_cabecalho(self.cfg["smtp"].get("nome_remetente", ""))
        msg["From"] = formataddr((nome_rem, remetente)) if nome_rem else remetente
        msg["To"] = ", ".join(para)
        msg["Subject"] = assunto
        msg.set_content(html_para_texto(envio["corpo"]))
        msg.add_alternative(envio["corpo"], subtype="html")

        for tentativa in (1, 2):
            if self.conexao is None:
                self._conectar()
            try:
                self.conexao.send_message(msg, from_addr=remetente, to_addrs=para + oculta)  # CCO: só no envelope, nunca nos cabeçalhos
                return
            except smtplib.SMTPServerDisconnected:
                self.conexao = None  # servidor encerrou a sessão: reconecta uma vez
                if tentativa == 2:
                    raise ErroFatal("A conexão com o servidor SMTP foi perdida.") from None
            except smtplib.SMTPRecipientsRefused as e:
                raise ErroEnvio(f"Destinatário recusado pelo servidor: {', '.join(e.recipients)}") from None
            except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as e:
                if b"SendAsDenied" in (e.smtp_error or b""):
                    raise ErroFatal(f"O servidor recusou o remetente '{remetente}': a conta SMTP não "
                                    "tem permissão para enviar como esse endereço.") from None
                raise ErroEnvio(f"O servidor recusou a mensagem (código {e.smtp_code}).") from None
            except smtplib.SMTPException as e:
                raise ErroEnvio(f"Erro no envio SMTP ({type(e).__name__}).") from None


def buscar_recusas(desde: datetime, assuntos) -> dict:
    """
    Procura na Caixa de Entrada do Outlook avisos de não entrega (NDR) recebidos após `desde`
    para os assuntos informados. O Exchange não devolve erro no Send(); ele recusa depois e
    avisa por e-mail. Retorna {assunto: motivo}.
    """
    import win32com.client
    ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    itens = ns.GetDefaultFolder(6).Items
    itens.Sort("[CreationTime]", True)
    pendentes = set(assuntos)
    recusas = {}
    for item in itens:
        try:
            # o Outlook entrega a hora local marcada como UTC; compara sem fuso
            if item.CreationTime.replace(tzinfo=None) < desde:
                break
            if "NDR" not in item.MessageClass.upper():
                continue
            assunto_ndr, corpo = item.Subject or "", item.Body or ""
        except Exception:
            continue
        for assunto in list(pendentes):
            if assunto in assunto_ndr:
                texto = re.sub(r"\s+", " ", corpo)
                motivo = re.search(r"(Você não possui permissão[^.]*|You can't send[^.]*|"
                                   r"não foi possível encontrar[^.]*|[^.]*não existe[^.]*)", texto, re.I)
                recusas[assunto] = motivo.group(1).strip() if motivo else texto[:200]
                pendentes.discard(assunto)
    return recusas


def _preparar_log():
    """Se o log for do formato antigo (sem chave/assunto), arquiva e começa um novo."""
    if not ARQUIVO_LOG.exists():
        return
    with open(ARQUIVO_LOG, newline="", encoding="utf-8-sig") as f:
        cabecalho = next(csv.reader(f, delimiter=";"), [])
    if cabecalho != CABECALHO_LOG:
        ARQUIVO_LOG.rename(ARQUIVO_LOG.with_name(
            f"log_envios_anterior_{datetime.now():%Y%m%d_%H%M%S}.csv"))


def registrar_log(doc, nome, email, status, assunto=""):
    """Registra o envio. O CPF/CNPJ vai mascarado; senha e conteúdo do e-mail nunca são gravados."""
    _preparar_log()
    novo = not ARQUIVO_LOG.exists()
    with open(ARQUIVO_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(CABECALHO_LOG)
        w.writerow([datetime.now().strftime("%d/%m/%Y %H:%M:%S"), mascarar_documento(doc),
                    limpar_cabecalho(nome), email, limpar_cabecalho(assunto),
                    limpar_cabecalho(status), chave_envio(doc, assunto) if assunto else ""])


def envios_anteriores() -> dict:
    """{chave: data_hora} dos extratos já enviados com sucesso (recusas posteriores anulam o envio)."""
    if not ARQUIVO_LOG.exists():
        return {}
    enviados = {}
    with open(ARQUIVO_LOG, newline="", encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            chave = linha.get("chave")
            if not chave:
                continue
            if linha.get("status") == "ENVIADO":
                enviados[chave] = linha.get("data_hora", "")
            elif linha.get("status", "").startswith("RECUSADO"):
                enviados.pop(chave, None)
    return enviados


def ja_enviado(envio, anteriores=None):
    """Data/hora do envio anterior deste mesmo extrato, ou None."""
    anteriores = envios_anteriores() if anteriores is None else anteriores
    return anteriores.get(chave_envio(envio["doc"], envio.get("assunto", "")))


# ------------------------------------------------------------------ linha de comando

def main():
    ap = argparse.ArgumentParser(description="Envio de extrato de fretes para agregados")
    alvo = ap.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--cnpj", nargs="+", help="Um ou mais CNPJ/CPF (com ou sem pontuação)")
    alvo.add_argument("--todos", action="store_true", help="Todos os agregados da planilha")
    alvo.add_argument("--listar", action="store_true", help="Apenas lista os agregados")
    ap.add_argument("--enviar", action="store_true",
                    help="Envia de fato. Sem isso, só gera as prévias em HTML")
    ap.add_argument("--planilha", help="Planilha a usar (sobrescreve o config.ini)")
    ap.add_argument("--periodo", help="Sobrescreve o período/semana do e-mail")
    ap.add_argument("--reenviar", action="store_true",
                    help="Envia mesmo que o extrato já tenha sido enviado antes")
    ap.add_argument("--config", default=str(ARQUIVO_CONFIG))
    args = ap.parse_args()

    cfg = carregar_config(args.config)
    try:
        df, emails = carregar_dados(cfg, args.planilha)
    except ErroPlanilha as e:
        sys.exit(str(e))

    docs = None if (args.todos or args.listar) else [normalizar_documento(c) for c in args.cnpj]
    envios = preparar_envios(cfg, df, emails, docs, args.periodo or cfg["email"].get("periodo", ""))

    if args.listar:
        for e in envios:
            print(f"{formatar_documento(e['doc']):<20} {e['nome']:<40} "
                  f"{e['fretes']:>3} frete(s)  {e['email'] or '** SEM E-MAIL **'}")
        return

    if args.enviar and len(envios) > 1:
        resp = input(f"Confirmar envio de {len(envios)} e-mail(s)? (s/n): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            return

    PASTA_PREVIA.mkdir(exist_ok=True)
    remetente = cfg["email"].get("enviar_como", "")
    cco = cco_padrao(cfg)
    intervalo = cfg["email"].getfloat("intervalo_segundos", 5)
    anteriores = envios_anteriores()
    inicio = datetime.now()
    enviados = []
    ok = falhas = 0

    with Enviador(cfg) as enviador:
        for e in envios:
            if e.get("erro"):
                print(f"[AVISO] {formatar_documento(e['doc'])}: {e['erro']}")
                falhas += 1
                continue

            if not args.enviar:
                arq = PASTA_PREVIA / f"{e['doc']}_{re.sub(r'[^\w]+', '_', e['nome'])[:40]}.html"
                arq.write_text(e["corpo"], encoding="utf-8")
                print(f"[PRÉVIA] {e['assunto']} -> {e['email'] or 'SEM E-MAIL'} | {arq.name}")
                ok += 1
                continue

            if not e["email"]:
                print(f"[ERRO] {e['nome']} ({formatar_documento(e['doc'])}): sem e-mail cadastrado")
                registrar_log(e["doc"], e["nome"], "", "SEM E-MAIL", e["assunto"])
                falhas += 1
                continue
            anterior = ja_enviado(e, anteriores)
            if anterior and not args.reenviar:
                print(f"[PULADO] {e['nome']}: este extrato já foi enviado em {anterior} "
                      "(use --reenviar para enviar de novo)")
                continue
            if enviados:
                time.sleep(intervalo)
            try:
                enviador.enviar(e, remetente, cco)
                print(f"[ENVIADO] {e['nome']} -> {e['email']} | {e['fretes']} frete(s)")
                registrar_log(e["doc"], e["nome"], e["email"], "ENVIADO", e["assunto"])
                enviados.append(e)
                ok += 1
            except ErroEnvio as erro:
                print(f"[ERRO] {e['nome']} -> {e['email']}: {erro}")
                registrar_log(e["doc"], e["nome"], e["email"], f"ERRO: {erro}", e["assunto"])
                falhas += 1
                if isinstance(erro, ErroFatal):
                    print("Envio interrompido: o erro afeta todos os e-mails do lote.")
                    break

    if enviados and cfg["email"].get("metodo", "outlook") == "outlook":
        print(f"\nAguardando {ESPERA_RECUSAS}s por avisos de não entrega do servidor...")
        time.sleep(ESPERA_RECUSAS)
        recusas = buscar_recusas(inicio, [e["assunto"] for e in enviados])
        for e in enviados:
            if e["assunto"] in recusas:
                print(f"[RECUSADO] {e['nome']} -> {e['email']}: {recusas[e['assunto']]}")
                registrar_log(e["doc"], e["nome"], e["email"], f"RECUSADO: {recusas[e['assunto']]}",
                              e["assunto"])
                ok -= 1
                falhas += 1

    acao = "enviado(s)" if args.enviar else f"prévia(s) gerada(s) em {PASTA_PREVIA}"
    print(f"\nConcluído: {ok} {acao}, {falhas} com problema.")


if __name__ == "__main__":
    main()
