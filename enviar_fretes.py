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
import html
import os
import re
import shutil
import smtplib
import sys
import time
import unicodedata
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

# no executável, config e log ficam ao lado do .exe
if getattr(sys, "frozen", False):
    PASTA = Path(sys.executable).resolve().parent
else:
    PASTA = Path(__file__).resolve().parent
PASTA_PREVIA = PASTA / "previas"
ARQUIVO_LOG = PASTA / "log_envios.csv"
ARQUIVO_CONFIG = PASTA / "config.ini"
ESPERA_RECUSAS = 20  # segundos aguardando avisos de não entrega após o envio


class ErroPlanilha(Exception):
    pass


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


# ------------------------------------------------------------------ config e planilha

def carregar_config(caminho=None) -> configparser.ConfigParser:
    caminho = Path(caminho or ARQUIVO_CONFIG)
    if not caminho.exists() and getattr(sys, "frozen", False):
        # primeira execução do .exe: cria o config.ini padrão ao lado do executável
        shutil.copy(Path(sys._MEIPASS) / "config.ini", caminho)
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

    estilo_th = "background:#1f4e79;color:#fff;padding:8px;border:1px solid #ccc;text-align:left"
    estilo_td = "padding:6px 8px;border:1px solid #ccc"
    cab = "".join(f'<th style="{estilo_th}">{html.escape(c)}</th>' for c in colunas)

    linhas = []
    for i, (_, f) in enumerate(fretes.iterrows()):
        fundo = "#f2f6fa" if i % 2 else "#fff"
        tds = "".join(
            f'<td style="{estilo_td};{"text-align:right" if c in moeda else ""}">'
            f'{html.escape(celula(c, f[c]))}</td>' for c in colunas)
        linhas.append(f'<tr style="background:{fundo}">{tds}</tr>')

    total = ""
    if any(c in moeda for c in colunas):
        tds = "".join(
            f'<td style="{estilo_td};text-align:right;font-weight:bold">'
            f'{formatar_moeda(fretes[c].sum()) if c in moeda else ("TOTAL" if j == 0 else "")}</td>'
            for j, c in enumerate(colunas))
        total = f'<tr style="background:#dde7f0">{tds}</tr>'

    assinatura = html.escape(cfg["email"].get("assinatura", ""))
    return f"""<html><body style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#222">
<p>Olá, <b>{html.escape(nome)}</b>,</p>
<p>Segue o extrato dos seus fretes referente a <b>{html.escape(periodo)}</b>.<br>
CNPJ/CPF: {formatar_documento(doc)} &nbsp;|&nbsp; Quantidade de fretes: {len(fretes)}</p>
<table style="border-collapse:collapse;font-size:13px">
<thead><tr>{cab}</tr></thead>
<tbody>{''.join(linhas)}{total}</tbody>
</table>
<p>Este é um e-mail automático. Por favor, não responda.</p>
<p>Em caso de dúvidas, favor entrar em contato pelo e-mail agregados@tcm.com.br</p>
<p>Atenciosamente,<br>{assinatura}</p>
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
        assunto = cfg["email"]["assunto"].format(
            nome=nome, documento=formatar_documento(doc), periodo=periodo, semana=semana)
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


def enviar_outlook(para, assunto, corpo, remetente="", cc=""):
    import win32com.client  # pywin32
    outlook = win32com.client.Dispatch("Outlook.Application")
    msg = outlook.CreateItem(0)
    msg.To = para
    if cc:
        msg.CC = cc
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


def enviar_smtp(cfg, para, assunto, corpo, remetente="", cc=""):
    s = cfg["smtp"]
    senha = os.environ.get("SMTP_SENHA")
    if not senha:
        raise RuntimeError("Defina a variável de ambiente SMTP_SENHA com a senha do e-mail.")
    remetente = remetente or s["remetente"]
    msg = MIMEMultipart("alternative")
    msg["From"] = remetente
    msg["To"] = para
    destinos = [e.strip() for e in para.split(";") if e.strip()]
    if cc:
        msg["Cc"] = cc
        destinos += [e.strip() for e in cc.split(";") if e.strip()]
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "html", "utf-8"))
    with smtplib.SMTP(s["servidor"], s.getint("porta")) as srv:
        srv.starttls()
        srv.login(s["usuario"], senha)
        srv.sendmail(remetente, destinos, msg.as_string())


def enviar(cfg, envio, remetente="", cc=""):
    if cfg["email"].get("metodo", "outlook") == "outlook":
        enviar_outlook(envio["email"], envio["assunto"], envio["corpo"], remetente, cc)
    else:
        enviar_smtp(cfg, envio["email"], envio["assunto"], envio["corpo"], remetente, cc)


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


def registrar_log(doc, nome, email, status):
    novo = not ARQUIVO_LOG.exists()
    with open(ARQUIVO_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["data_hora", "cnpj_cpf", "nome", "email", "status"])
        w.writerow([datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    formatar_documento(doc), nome, email, status])


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
    cc = cfg["email"].get("cc", "")
    intervalo = cfg["email"].getfloat("intervalo_segundos", 5)
    inicio = datetime.now()
    enviados = []
    ok = falhas = 0

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
            registrar_log(e["doc"], e["nome"], "", "SEM E-MAIL")
            falhas += 1
            continue
        if enviados:
            time.sleep(intervalo)
        try:
            enviar(cfg, e, remetente, cc)
            print(f"[ENVIADO] {e['nome']} -> {e['email']} | {e['fretes']} frete(s)")
            registrar_log(e["doc"], e["nome"], e["email"], "ENVIADO")
            enviados.append(e)
            ok += 1
        except Exception as erro:
            print(f"[ERRO] {e['nome']} -> {e['email']}: {erro}")
            registrar_log(e["doc"], e["nome"], e["email"], f"ERRO: {erro}")
            falhas += 1

    if enviados and cfg["email"].get("metodo", "outlook") == "outlook":
        print(f"\nAguardando {ESPERA_RECUSAS}s por avisos de não entrega do servidor...")
        time.sleep(ESPERA_RECUSAS)
        recusas = buscar_recusas(inicio, [e["assunto"] for e in enviados])
        for e in enviados:
            if e["assunto"] in recusas:
                print(f"[RECUSADO] {e['nome']} -> {e['email']}: {recusas[e['assunto']]}")
                registrar_log(e["doc"], e["nome"], e["email"], f"RECUSADO: {recusas[e['assunto']]}")
                ok -= 1
                falhas += 1

    acao = "enviado(s)" if args.enviar else f"prévia(s) gerada(s) em {PASTA_PREVIA}"
    print(f"\nConcluído: {ok} {acao}, {falhas} com problema.")


if __name__ == "__main__":
    main()
