# Envio de Extrato de Fretes para Agregados

Lê a planilha de fretes, separa os fretes de cada CNPJ/CPF e envia um e-mail para cada
agregado com **apenas os fretes dele** (tabela no corpo do e-mail e total no final), pelo Outlook.

## Usando o executável
1. Abra `dist\Extrato Fretes Agregados.exe` (o Outlook precisa estar configurado no computador).
2. Clique em **Selecionar planilha...** e escolha a planilha (abas de fretes + `Emails`).
3. Na primeira abertura, informe o **e-mail remetente**, a **senha** e o **CC padrão** (janela de credenciais;
   o botão **Credenciais...** altera depois). Ficam só no arquivo `.env` deste computador.
4. Selecione os agregados (todos com e-mail já vêm marcados). Dê dois cliques ou use
   **Visualizar e-mail** para ver o e-mail no navegador.
5. Clique em **Enviar selecionados** e confirme.

Ao lado do `.exe` ficam:
- `config.ini`: colunas, assunto, assinatura (criado na primeira execução).
- `log_envios.csv`: histórico de envios.
- `preferencias.json`: lembra a última planilha, remetente e CC.

Para distribuir, basta copiar o `.exe` (e, se tiver alterado, o `config.ini`).

## Gerar o executável e publicar uma atualização
1. Aumente o número em `versao.py` (ex.: `1.2.0`).
2. `powershell -File build.ps1` gera `dist\Extrato Fretes Agregados.exe` e o arquivo `.sha256`.
3. No GitHub, crie uma **Release** com a tag `v1.2.0` anexando os **dois** arquivos de `dist\`.

Ao abrir, o executável consulta a última Release do repositório definido em `[atualizacao]` do
`config.ini`; se a versão for maior, baixa, confere o SHA-256, se substitui e reinicia sozinho.
Exige Release **pública** (sem token). Desligue com `ativo = nao`. Falhas de rede são ignoradas.

## Linha de comando (opcional)
```
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --listar
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --todos            # só prévias
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --todos --enviar
```
