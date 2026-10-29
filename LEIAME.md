# Envio de Extrato de Fretes para Agregados

Lê a planilha de fretes, separa os fretes de cada CNPJ/CPF e envia um e-mail para cada
agregado com **apenas os fretes dele** (tabela no corpo do e-mail e total no final), pelo Outlook.

## Usando o executável
1. Abra `dist\Extrato Fretes Agregados.exe` (o Outlook precisa estar configurado no computador).
2. Clique em **Selecionar planilha...** e escolha a planilha (abas de fretes + `Emails`).
3. Confira **Remetente** (vazio = e-mail logado no Outlook) e **Cópia (CC)** (padrão: agregados@tcm.com.br).
4. Selecione os agregados (todos com e-mail já vêm marcados). Dê dois cliques ou use
   **Visualizar e-mail** para ver o e-mail no navegador.
5. Clique em **Enviar selecionados** e confirme.

Ao lado do `.exe` ficam:
- `config.ini`: colunas, assunto, assinatura (criado na primeira execução).
- `log_envios.csv`: histórico de envios.
- `preferencias.json`: lembra a última planilha, remetente e CC.

Para distribuir, basta copiar o `.exe` (e, se tiver alterado, o `config.ini`).

## Gerar o executável novamente (após alterar o código)
```
pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name "Extrato Fretes Agregados" --add-data "config.ini;." --hidden-import openpyxl --hidden-import pythoncom app.py
```

## Linha de comando (opcional)
```
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --listar
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --todos            # só prévias
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --todos --enviar
```
