"""Tela do Extrato de Fretes: escolhe a planilha, confere os agregados e envia os e-mails."""

import html
import json
import queue
import tempfile
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import enviar_fretes as ef

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


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = ef.carregar_config()
        self.prefs = ler_prefs()
        self.envios = {}
        self.fila = queue.Queue()
        self.enviando = False

        root.title("Extrato de Fretes - Agregados")
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

        ttk.Label(topo, text="Remetente:").grid(row=1, column=0, sticky="w", pady=3)
        self.var_remetente = tk.StringVar(
            value=self.prefs.get("remetente", self.cfg["email"].get("enviar_como", "")))
        ttk.Entry(topo, textvariable=self.var_remetente).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(topo, text="vazio = e-mail logado no Outlook", foreground="gray").grid(
            row=1, column=2, sticky="w")

        ttk.Label(topo, text="Cópia (CC):").grid(row=2, column=0, sticky="w", pady=3)
        self.var_cc = tk.StringVar(value=self.prefs.get("cc", self.cfg["email"].get("cc", "")))
        ttk.Entry(topo, textvariable=self.var_cc).grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Label(topo, text="separe vários com ;", foreground="gray").grid(
            row=2, column=2, sticky="w")

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
        self.btn_enviar = ttk.Button(botoes, text="Enviar selecionados", command=self.enviar_selecionados)
        self.btn_enviar.pack(side="right")
        self.var_resumo = tk.StringVar(value="Selecione a planilha para começar.")
        ttk.Label(botoes, textvariable=self.var_resumo).pack(side="left", padx=15)

        self.log = tk.Text(root, height=7, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="x", padx=10, pady=(0, 10))

        self.root.after(150, self.processar_fila)

    # -------------------------------------------------------------- ações

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
        selecionados = [self.envios[d] for d in self.tree.selection()]
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
        texto = (f"Enviar {len(validos)} e-mail(s)?\n\n"
                 f"Remetente: {remetente or 'e-mail logado no Outlook'}\n"
                 f"Cópia (CC): {cc or '-'}")
        if sem_email:
            texto += f"\n\n{len(sem_email)} selecionado(s) sem e-mail serão ignorados."
        if not messagebox.askyesno("Confirmar envio", texto):
            return

        self.prefs.update(remetente=remetente, cc=cc)
        salvar_prefs(self.prefs)
        self.enviando = True
        self.btn_enviar.configure(state="disabled")
        threading.Thread(target=self._enviar_thread, args=(validos, remetente, cc), daemon=True).start()

    def _enviar_thread(self, envios, remetente, cc):
        import pythoncom  # o Outlook (COM) precisa ser inicializado em cada thread
        pythoncom.CoInitialize()
        ok = falhas = 0
        try:
            for e in envios:
                self.fila.put(("status", e["doc"], "Enviando...", ""))
                try:
                    ef.enviar(self.cfg, e, remetente, cc)
                    ef.registrar_log(e["doc"], e["nome"], e["email"], "ENVIADO")
                    self.fila.put(("status", e["doc"], "Enviado", "enviado"))
                    self.fila.put(("log", f"[ENVIADO] {e['nome']} -> {e['email']}"))
                    ok += 1
                except Exception as erro:
                    ef.registrar_log(e["doc"], e["nome"], e["email"], f"ERRO: {erro}")
                    self.fila.put(("status", e["doc"], "Erro", "erro"))
                    self.fila.put(("log", f"[ERRO] {e['nome']} -> {e['email']}: {erro}"))
                    falhas += 1
        finally:
            pythoncom.CoUninitialize()
            self.fila.put(("fim", ok, falhas))

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
                elif item[0] == "fim":
                    _, ok, falhas = item
                    self.enviando = False
                    self.btn_enviar.configure(state="normal")
                    self.escrever_log(f"Concluído: {ok} enviado(s), {falhas} com erro.")
                    messagebox.showinfo("Envio concluído", f"{ok} e-mail(s) enviado(s)\n{falhas} com erro")
        except queue.Empty:
            pass
        self.root.after(150, self.processar_fila)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
