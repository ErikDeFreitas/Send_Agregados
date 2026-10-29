"""Gera uma planilha_fretes.xlsx de exemplo para testar o sistema."""

from pathlib import Path

import pandas as pd

dados = [
    ("12.345.678/0001-90", "Transportes Silva LTDA", "silva@exemplo.com", "02/10/2026", "1001", "Campinas/SP", "Curitiba/PR", 3500.00, 150.00),
    ("12.345.678/0001-90", "Transportes Silva LTDA", "silva@exemplo.com", "09/10/2026", "1015", "Santos/SP", "Goiânia/GO", 4200.00, 0.00),
    ("12.345.678/0001-90", "Transportes Silva LTDA", "silva@exemplo.com", "21/10/2026", "1042", "Campinas/SP", "Uberlândia/MG", 2800.00, 80.00),
    ("123.456.789-09", "João Pereira", "joao@exemplo.com", "05/10/2026", "1008", "Jundiaí/SP", "Belo Horizonte/MG", 2900.00, 0.00),
    ("123.456.789-09", "João Pereira", "joao@exemplo.com", "18/10/2026", "1033", "Sorocaba/SP", "Rio de Janeiro/RJ", 3100.00, 200.00),
    ("98.765.432/0001-10", "Rodo Express ME", "", "12/10/2026", "1020", "Campinas/SP", "Porto Alegre/RS", 5600.00, 300.00),
]
df = pd.DataFrame(dados, columns=["CNPJ/CPF", "Nome", "Email", "Data", "CTe", "Origem",
                                  "Destino", "Valor Frete", "Descontos"])
df["Valor Líquido"] = df["Valor Frete"] - df["Descontos"]

destino = Path(__file__).resolve().parent / "planilha_fretes.xlsx"
df.to_excel(destino, sheet_name="Fretes", index=False)
print(f"Planilha de exemplo criada: {destino}")
