# Envio de Extrato de Fretes para Agregados (RoboAgregado)

Lê a planilha de fretes, separa os fretes de cada CNPJ/CPF e envia um e-mail para cada
agregado com **apenas os fretes dele** (tabela no corpo do e-mail e total no final).

O programa é o pacote `src/robo_agregado/`, construído sobre a biblioteca de interface
[`tcm-ui`](https://github.com/ErikDeFreitas/Tcm-ui). Pode rodar sozinho (`RoboAgregado.exe`)
ou dentro do Sistema Financeiro (grupo `SF-RoboAgregado`).

## Estrutura
```
main.py                      ponto de entrada do .exe avulso
build.ps1                    gera dist\RoboAgregado.exe e o .sha256
src/robo_agregado/
  modulo.py                  registro do módulo (MODULO)
  tela.py                    tela do módulo
  dados.py                   pasta de dados, config.ini, migração
  enviar_fretes.py           leitura da planilha, e-mail e linha de comando
  config.ini                 configuração padrão
tests/                       testes (pytest)
gerar_planilha_exemplo.py    cria uma planilha fictícia para testar
```

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
- `logs\robo_agregado.log`: log de erros do programa.

Para distribuir, basta o `.exe` (baixe em **Releases** no GitHub).

## Rodando pelo Python
```
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python main.py
```
Pelo Python os dados ficam na mesma pasta do `.exe` (`%LOCALAPPDATA%\RoboAgregado`). Para usar outra
pasta (por exemplo, em testes), defina a variável de ambiente `ROBO_AGREGADO_DADOS`.

## Testes
```
.venv\Scripts\python -m pytest -q
```
Os testes não escrevem no registro, não usam a pasta real de dados e não enviam e-mail.

## Publicar uma atualização
1. Suba `__version__` em `src/robo_agregado/__init__.py` (ex.: `2.0.1`).
2. Crie a tag igual, com `v` na frente, e envie: `git tag v2.0.1` e `git push origin v2.0.1`.
3. O workflow `.github/workflows/release.yml` confere que a tag bate com `__version__`, roda os testes,
   gera o `.exe` e o `.sha256` e cria a Release com os dois arquivos.

Antes de criar a tag do RoboAgregado, a tag `v1.1.0` do `tcm-ui` precisa existir no GitHub (a dependência
`tcm-ui@v1.1.0` é instalada pelo workflow; sem ela o `pip install` falha).

Ao abrir, o executável consulta a última Release do repositório definido em `MODULO.repositorio`
(`ErikDeFreitas/Send_Agregados`); se a versão for maior, baixa, confere o SHA-256, se substitui e reinicia sozinho.
Exige Release **pública** (sem token). Desligue com `[atualizacao] ativo = nao`. Falhas de rede são ignoradas.

## Linha de comando (opcional)
```
python -m robo_agregado.enviar_fretes --planilha "C:\caminho\planilha.xlsx" --listar
python -m robo_agregado.enviar_fretes --planilha "C:\caminho\planilha.xlsx" --todos            # só prévias
python -m robo_agregado.enviar_fretes --planilha "C:\caminho\planilha.xlsx" --todos --enviar
```
