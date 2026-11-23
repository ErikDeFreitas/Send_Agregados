"""Gera uma planilha_fretes.xlsx FICTICIA (aba VW + aba Emails) no formato do config.ini padrao."""

from pathlib import Path

import pandas as pd

# Documentos e e-mails inventados (nenhum dado real).
fretes = [
    ("11.111.111/0001-11", "Agregado Exemplo A", "1001", "MAN-01", "CIOT-0001", "AAA0A00", "Campinas/SP", "Curitiba/PR", 150.00, 3500.00, "VW SEMANA 42 - VCTO 04-11-2026", "02/10/2026"),
    ("11.111.111/0001-11", "Agregado Exemplo A", "1015", "MAN-02", "CIOT-0002", "AAA0A00", "Santos/SP", "Goiânia/GO", 0.00, 4200.00, "VW SEMANA 42 - VCTO 04-11-2026", "09/10/2026"),
    ("111.111.111-11", "Agregado Exemplo B", "1008", "MAN-03", "CIOT-0003", "BBB1B11", "Jundiaí/SP", "Belo Horizonte/MG", 0.00, 2900.00, "VW SEMANA 42 - VCTO 04-11-2026", "05/10/2026"),
    ("22.222.222/0001-22", "Agregado Exemplo C", "1020", "MAN-04", "CIOT-0004", "CCC2C22", "Campinas/SP", "Porto Alegre/RS", 300.00, 5600.00, "VW SEMANA 42 - VCTO 04-11-2026", "12/10/2026"),
]
colunas = ["CNPJ / CPF", "Agregado", "Nº Referência", "Manifesto", "CIOT Sistema", "Placa Veiculo",
           "Origem", "Destino", "Adiantamento Pago", "Saldo Final", "Tipo Operação", "Data do pagamento"]
emails = [
    ("11.111.111/0001-11", "agregado.a@exemplo.invalid"),
    ("111.111.111-11", "agregado.b@exemplo.invalid"),
    ("22.222.222/0001-22", ""),
]

destino = Path(__file__).resolve().parent / "planilha_fretes.xlsx"  # *.xlsx esta no .gitignore
with pd.ExcelWriter(destino) as xls:
    pd.DataFrame(fretes, columns=colunas).to_excel(xls, sheet_name="VW", index=False)
    pd.DataFrame(emails, columns=["CNPJ / CPF", "Email"]).to_excel(xls, sheet_name="Emails", index=False)
print(f"Planilha de exemplo criada: {destino}")
