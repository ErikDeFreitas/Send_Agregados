# Envio de Extrato de Fretes para Agregados

Lê a planilha de fretes, separa os fretes de cada CNPJ/CPF e envia um e-mail para cada
agregado com **apenas os fretes dele** (tabela no corpo do e-mail e total no final), pelo Outlook.

## Usando o executável
1. Abra `RoboAgregado.exe` (pode ficar em qualquer pasta; não precisa instalar nada).
2. Na primeira abertura, informe o **e-mail remetente**, a **senha** e o **CCO padrão** (cópia oculta,
   opcional). O botão **Credenciais...** altera depois. Ficam só no arquivo `.env` deste computador.
3. Clique em **Selecionar planilha...** e escolha a planilha (abas de fretes + `Emails`).
4. Selecione os agregados (todos com e-mail já vêm marcados). Dê dois cliques ou use
   **Visualizar e-mail** para ver o e-mail no navegador.
5. Clique em **Enviar selecionados** e confirme. O remetente é sempre o das credenciais.

Os arquivos do programa ficam em `%LOCALAPPDATA%\RoboAgregado` (botão **Pasta de dados**), não ao lado do `.exe`:
- `config.ini`: colunas, assunto, assinatura (criado na primeira execução).
- `.env`: remetente, senha e CCO.
- `log_envios.csv`: histórico de envios.
- `preferencias.json`: lembra a última planilha, o CCO e o intervalo.

Para distribuir, basta o `.exe` (baixe em **Releases** no GitHub). Arquivos de versões antigas
que estiverem ao lado do `.exe` são movidos para a pasta de dados automaticamente.

## Gerar o executável e publicar uma atualização
1. Aumente o número em `versao.py` (ex.: `1.3.0`).
2. `powershell -File build.ps1` gera `dist\RoboAgregado.exe` e o arquivo `.sha256`.
3. No GitHub, crie uma **Release** com a tag `v1.3.0` anexando os **dois** arquivos de `dist\`.

Ao abrir, o executável consulta a última Release do repositório definido em `[atualizacao]` do
`config.ini`; se a versão for maior, baixa, confere o SHA-256, se substitui e reinicia sozinho.
Exige Release **pública** (sem token). Desligue com `ativo = nao`. Falhas de rede são ignoradas.

## Linha de comando (opcional)
```
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --listar
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --todos            # só prévias
python enviar_fretes.py --planilha "C:\caminho\planilha.xlsx" --todos --enviar
```
