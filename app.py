"""Tela do Extrato de Fretes: escolhe a planilha, confere os agregados e envia os e-mails."""

import html
import json
import os
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import atualizador
import enviar_fretes as ef
from versao import VERSAO

ARQUIVO_PREFS = ef.PASTA / "preferencias.json"


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


class DialogoCredenciais(tk.Toplevel):
    """Pede usuário e senha do remetente, testa o login e grava no .env."""

    def __init__(self, pai, cfg):
        super().__init__(pai)
        self.cfg, self.salvo = cfg, False
        self.title("Credenciais do remetente")
        self.resizable(False, False)
        self.transient(pai)

        corpo = ttk.Frame(self, padding=15)
        corpo.pack(fill="both", expand=True)
        corpo.columnconfigure(1, weight=1)
        ttk.Label(corpo, text="Informe o e-mail remetente e a senha da conta que enviará os extratos.\n"
                              "Os dados ficam salvos só neste computador (arquivo .env).",
                  justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(corpo, text="E-mail:").grid(row=1, column=0, sticky="w", pady=3)
        self.var_usuario = tk.StringVar(value=os.environ.get("SMTP_USUARIO", ""))
        self.campo_usuario = ttk.Entry(corpo, textvariable=self.var_usuario, width=38)
        self.campo_usuario.grid(row=1, column=1, padx=(8, 0))
        ttk.Label(corpo, text="Senha:").grid(row=2, column=0, sticky="w", pady=3)
        self.var_senha = tk.StringVar()
        self.campo_senha = ttk.Entry(corpo, textvariable=self.var_senha, show="*", width=38)
        self.campo_senha.grid(row=2, column=1, padx=(8, 0))
        ttk.Label(corpo, text="CC padrão:").grid(row=3, column=0, sticky="w", pady=3)
        self.var_cc = tk.StringVar(value=ef.cc_padrao(cfg))
        ttk.Entry(corpo, textvariable=self.var_cc, width=38).grid(row=3, column=1, padx=(8, 0))
        ttk.Label(corpo, text="opcional; vários endereços separados por ;", foreground="gray").grid(
            row=4, column=1, sticky="w", padx=(8, 0))
        self.var_msg = tk.StringVar()
        ttk.Label(corpo, textvariable=self.var_msg, foreground="#b00020", wraplength=330,
                  justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botoes = ttk.Frame(corpo)
        botoes.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.btn_salvar = ttk.Button(botoes, text="Testar e salvar", command=self.salvar)
        self.btn_salvar.pack(side="left", padx=5)
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda _: self.salvar())
        self.bind("<Escape>", lambda _: self.destroy())
        (self.campo_senha if self.var_usuario.get() else self.campo_usuario).focus_set()
        self.grab_set()

    def salvar(self):
        usuario, senha = self.var_usuario.get().strip(), self.var_senha.get()
        cc = self.var_cc.get().strip()
        if ef.emails_invalidos(usuario) or not usuario:
            self.var_msg.set("Informe um e-mail válido.")
            return
        if not senha:
            self.var_msg.set("Informe a senha.")
            return
        if ef.emails_invalidos(cc):
            self.var_msg.set(f"CC inválido: {', '.join(ef.emails_invalidos(cc))}")
            return
        self.var_msg.set("Testando o login no servidor...")
        self.btn_salvar.configure(state="disabled")
        self.update_idletasks()
        try:
            ef.testar_login(self.cfg, usuario, senha)
        except ef.ErroEnvio as e:
            self.var_msg.set(str(e))
            self.btn_salvar.configure(state="normal")
            return
        try:
            ef.salvar_env(usuario, senha, cc)
        except OSError:
            self.var_msg.set("Não foi possível gravar o arquivo .env nesta pasta. "
                             "Mova o programa para uma pasta com permissão de escrita.")
            self.btn_salvar.configure(state="normal")
            return
        self.salvo = True
        self.destroy()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = ef.carregar_config()
        self.prefs = ler_prefs()
        self.envios = {}
        self.fila = queue.Queue()
        self.enviando = False
        self.parar = threading.Event()

        root.title(f"Extrato de Fretes - Agregados (v{VERSAO})")
        root.geometry("980x620")
        root.minsize(800, 500)

        topo = ttk.Frame(root, padding=10)
        topo.pack(fill="x")
        topo.columnconfigure(1, weight=1)

        ttk.Label(topo, text="Planilha:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_planilha = tk.StringVar()
        ttk.Entry(topo, textvariable=self.var_planilha, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=5)
        ttk.Button(topo, text="Selecionar planilha...", command=self.selecionar_planilha).grid(
            row=0, column=2, sticky="ew")

        # preferências separadas por método, para valores do Outlook não valerem no SMTP
        self.metodo = self.cfg["email"].get("metodo", "outlook").strip().lower()
        self.chave_rem, self.chave_cc = f"remetente_{self.metodo}", f"cc_{self.metodo}"
        padrao = ef.remetente_padrao(self.cfg)

        ttk.Label(topo, text="Remetente:").grid(row=1, column=0, sticky="w", pady=3)
        self.var_remetente = tk.StringVar(
            value=self.prefs.get(self.chave_rem, self.cfg["email"].get("enviar_como", "")))
        ttk.Entry(topo, textvariable=self.var_remetente).grid(row=1, column=1, sticky="ew", padx=5)
        dica = f"vazio = {padrao}" if padrao else "vazio = e-mail logado no Outlook"
        ttk.Label(topo, text=dica, foreground="gray").grid(row=1, column=2, sticky="w")

        ttk.Label(topo, text="Cópia (CC):").grid(row=2, column=0, sticky="w", pady=3)
        self.var_cc = tk.StringVar(
            value=self.prefs.get(self.chave_cc, ef.cc_padrao(self.cfg)))
        ttk.Entry(topo, textvariable=self.var_cc).grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Label(topo, text="separe vários com ;", foreground="gray").grid(
            row=2, column=2, sticky="w")

        ttk.Label(topo, text="Intervalo (s):").grid(row=3, column=0, sticky="w", pady=3)
        self.var_intervalo = tk.StringVar(value=str(
            self.prefs.get("intervalo", self.cfg["email"].get("intervalo_segundos", "5"))))
        ttk.Spinbox(topo, from_=0, to=300, width=6, textvariable=self.var_intervalo).grid(
            row=3, column=1, sticky="w", padx=5)
        ttk.Label(topo, text="espera entre um envio e outro", foreground="gray").grid(
            row=3, column=2, sticky="w")

        meio = ttk.Frame(root, padding=(10, 0))
        meio.pack(fill="both", expand=True)
        colunas = ("doc", "nome", "fretes", "total", "email", "status")
        self.tree = ttk.Treeview(meio, columns=colunas, show="headings", selectmode="extended")
        for col, titulo, largura, ancora in [
            ("doc", "CNPJ/CPF", 140, "w"), ("nome", "Agregado", 260, "w"),
            ("fretes", "Fretes", 60, "center"), ("total", "Total", 110, "e"),
            ("email", "E-mail", 220, "w"), ("status", "Status", 120, "w")]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor=ancora)
        self.tree.tag_configure("sem_email", foreground="#b00020")
        self.tree.tag_configure("enviado", foreground="#1b7f3b")
        self.tree.tag_configure("erro", foreground="#b00020")
        barra = ttk.Scrollbar(meio, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _: self.visualizar())

        botoes = ttk.Frame(root, padding=10)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Selecionar todos",
                   command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left")
        ttk.Button(botoes, text="Visualizar e-mail", command=self.visualizar).pack(side="left", padx=5)
        if self.metodo == "smtp":
            ttk.Button(botoes, text="Credenciais...", command=self.pedir_credenciais).pack(
                side="left", padx=5)
        self.btn_enviar = ttk.Button(botoes, text="Enviar selecionados", command=self.enviar_selecionados)
        self.btn_enviar.pack(side="right")
        self.btn_parar = ttk.Button(botoes, text="Parar", state="disabled", command=self.parar_envio)
        self.btn_parar.pack(side="right", padx=5)
        self.var_resumo = tk.StringVar(value="Selecione a planilha para começar.")
        ttk.Label(botoes, textvariable=self.var_resumo).pack(side="left", padx=15)

        self.log = tk.Text(root, height=7, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="x", padx=10, pady=(0, 10))

        self.root.after(150, self.processar_fila)
        if self.metodo == "smtp" and not ef.credenciais_ok():
            self.root.after(300, self.pedir_credenciais)  # primeira execução
        self.root.after(1000, self.verificar_atualizacao)

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
        messagebox.showinfo("Atualização", f"Nova versão {versao} instalada.\n"
                                           "O programa será reiniciado agora.")
        try:
            atualizador.aplicar_e_reiniciar(novo)
        except atualizador.ErroAtualizacao as e:
            novo.unlink(missing_ok=True)
            messagebox.showwarning("Atualização", f"{e}\nO programa continuará na versão atual.")
            return
        self.root.destroy()
        os._exit(0)

    # -------------------------------------------------------------- ações

    def pedir_credenciais(self) -> bool:
        dialogo = DialogoCredenciais(self.root, self.cfg)
        self.root.wait_window(dialogo)
        if dialogo.salvo:
            self.var_cc.set(os.environ.get("EMAIL_CC", ""))
            self.escrever_log(f"Credenciais salvas para {os.environ.get('SMTP_USUARIO')}.")
        return dialogo.salvo

    def escrever_log(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def selecionar_planilha(self):
        pasta = Path(self.prefs.get("planilha", "")).parent if self.prefs.get("planilha") else None
        caminho = filedialog.askopenfilename(
            title="Selecione a planilha de fretes",
            initialdir=str(pasta) if pasta and pasta.exists() else None,
            filetypes=[("Planilhas Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")])
        if caminho:
            self.carregar(caminho)

    def carregar(self, caminho):
        try:
            df, emails = ef.carregar_dados(self.cfg, caminho)
            envios = ef.preparar_envios(self.cfg, df, emails,
                                        periodo_fixo=self.cfg["email"].get("periodo", ""))
        except ef.ErroPlanilha as e:
            messagebox.showerror("Planilha inválida", str(e))
            return
        except PermissionError:
            messagebox.showerror("Planilha em uso",
                                 "Não foi possível ler a planilha. Feche-a no Excel e tente novamente.")
            return
        except Exception as e:
            messagebox.showerror("Erro ao ler a planilha", f"{type(e).__name__}: {e}")
            return

        self.var_planilha.set(caminho)
        self.prefs["planilha"] = caminho
        salvar_prefs(self.prefs)
        self.tree.delete(*self.tree.get_children())
        self.envios = {e["doc"]: e for e in envios}
        sem_email = 0
        for e in envios:
            if not e["email"]:
                sem_email += 1
            self.tree.insert("", "end", iid=e["doc"], tags=("" if e["email"] else "sem_email",), values=(
                ef.formatar_documento(e["doc"]), e["nome"], e["fretes"],
                ef.formatar_moeda(e["total"]) if e.get("total") is not None else "",
                e["email"] or "SEM E-MAIL", ""))
        self.tree.selection_set([d for d, e in self.envios.items() if e["email"]])
        resumo = f"{len(envios)} agregado(s) encontrados"
        if sem_email:
            resumo += f" | {sem_email} sem e-mail"
        self.var_resumo.set(resumo)
        self.escrever_log(f"Planilha carregada: {caminho} ({len(envios)} agregados)")

    def visualizar(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Visualizar", "Selecione um agregado na lista.")
            return
        e = self.envios[sel[0]]
        cc = self.var_cc.get().strip()
        cabecalho = (f'<div style="font-family:Segoe UI,Arial;font-size:13px;background:#f4f4f4;'
                     f'padding:10px;margin-bottom:15px;border:1px solid #ddd">'
                     f'<b>Para:</b> {html.escape(e["email"] or "SEM E-MAIL")}<br>'
                     f'<b>CC:</b> {html.escape(cc or "-")}<br>'
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
        selecionados =[self.envios[d] for d in self.tree.selection()]
        if not selecionados:
            messagebox.showinfo("Enviar", "Selecione ao menos um agregado na lista.")
            return
        sem_email = [e for e in selecionados if not e["email"]]
        validos = [e for e in selecionados if e["email"]]
        if not validos:
            messagebox.showwarning("Enviar", "Nenhum dos selecionados tem e-mail cadastrado.")
            return

        remetente = self.var_remetente.get().strip()
        cc = self.var_cc.get().strip()
        try:
            intervalo = max(0.0, float(self.var_intervalo.get().replace(",", ".")))
        except ValueError:
            messagebox.showwarning("Intervalo", "Informe o intervalo em segundos (ex.: 5).")
            return

        # validação dos endereços antes de enviar qualquer coisa
        problemas = ef.emails_invalidos(remetente) + ef.emails_invalidos(cc)
        if problemas:
            messagebox.showwarning("E-mail inválido",
                                   "Corrija o remetente/CC:\n" + "\n".join(problemas))
            return
        invalidos = [e for e in validos if ef.emails_invalidos(e["email"])]
        if invalidos:
            lista_inv = "\n".join(f"{e['nome']}: {e['email']}" for e in invalidos[:10])
            if not messagebox.askyesno(
                    "E-mails inválidos",
                    f"{len(invalidos)} agregado(s) com e-mail inválido na planilha:\n\n{lista_inv}"
                    "\n\nContinuar enviando apenas para os demais?"):
                return
            validos = [e for e in validos if e not in invalidos]
            if not validos:
                return

        # prevenção de duplicidade: mesmo extrato (agregado + assunto) já enviado
        anteriores = ef.envios_anteriores()
        repetidos = [(e, ef.ja_enviado(e, anteriores)) for e in validos if ef.ja_enviado(e, anteriores)]
        if repetidos:
            lista_rep = "\n".join(f"{e['nome']} (em {quando})" for e, quando in repetidos[:10])
            resp = messagebox.askyesnocancel(
                "Extrato já enviado",
                f"{len(repetidos)} agregado(s) já receberam este mesmo extrato:\n\n{lista_rep}\n\n"
                "Sim = reenviar para eles também\nNão = enviar só para os que ainda não receberam\n"
                "Cancelar = não enviar nada")
            if resp is None:
                return
            if resp is False:
                ja = {e["doc"] for e, _ in repetidos}
                validos = [e for e in validos if e["doc"] not in ja]
                if not validos:
                    messagebox.showinfo("Enviar", "Todos os selecionados já receberam este extrato.")
                    return

        rotulo_rem = remetente or ef.remetente_padrao(self.cfg) or "e-mail logado no Outlook"
        texto = (f"Enviar {len(validos)} e-mail(s)?\n\n"
                 f"Remetente: {rotulo_rem}\n"
                 f"Cópia (CC): {cc or '-'}\n"
                 f"Intervalo entre envios: {intervalo:g} s")
        if sem_email:
            texto += f"\n\n{len(sem_email)} selecionado(s) sem e-mail serão ignorados."
        if remetente and self.metodo == "outlook":
            texto += ("\n\nComo há remetente definido, o primeiro e-mail será verificado antes "
                      "de continuar (cerca de 20 s).")
        if not messagebox.askyesno("Confirmar envio", texto):
            return

        self.prefs.update({self.chave_rem: remetente, self.chave_cc: cc, "intervalo": f"{intervalo:g}"})
        salvar_prefs(self.prefs)
        self.enviando = True
        self.parar.clear()
        self.btn_enviar.configure(state="disabled")
        self.btn_parar.configure(state="normal")
        envios = [dict(e) for e in validos]  # cópia: marcações de recusa não afetam a lista
        threading.Thread(target=self._enviar_thread, args=(envios, remetente, cc, intervalo),
                         daemon=True).start()

    def parar_envio(self):
        self.parar.set()
        self.btn_parar.configure(state="disabled")
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

    def _enviar_thread(self, envios, remetente, cc, intervalo):
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
                    enviador.enviar(e, remetente, cc)
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
                                 "ou deixe o remetente vazio.")
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

    def processar_fila(self):
        try:
            while True:
                item = self.fila.get_nowait()
                if item[0] == "status":
                    _, doc, status, tag = item
                    self.tree.set(doc, "status", status)
                    self.tree.item(doc, tags=(tag,))
                elif item[0] == "log":
                    self.escrever_log(item[1])
                elif item[0] == "atualizar":
                    self._aplicar_atualizacao(item[1], item[2])
                elif item[0] == "fim":
                    _, ok, falhas, aviso = item
                    self.enviando = False
                    self.btn_enviar.configure(state="normal")
                    self.btn_parar.configure(state="disabled")
                    self.escrever_log(f"Concluído: {ok} enviado(s), {falhas} com erro/recusado.")
                    resumo = f"{ok} e-mail(s) enviado(s)\n{falhas} com erro ou recusado(s)"
                    if aviso:
                        messagebox.showwarning("Envio interrompido", f"{aviso}\n\n{resumo}")
                    else:
                        messagebox.showinfo("Envio concluído", resumo)
        except queue.Empty:
            pass
        self.root.after(150, self.processar_fila)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
