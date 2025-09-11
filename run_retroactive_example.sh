#!/bin/bash

# Script de exemplo para executar o relatório retroativo
# Para gerar relatório como se fosse executado em 25/08/2025

echo "=== Executando Relatório Financeiro Retroativo ==="
echo "Data de referência: 25/08/2025"
echo "======================================================"

# Ativa o ambiente virtual se disponível
if [ -d "myenv" ]; then
    echo "Ativando ambiente virtual..."
    source myenv/bin/activate
fi

# Executa o script retroativo
python3 financial_report_retroactive.py --date 25/08/2025

echo "======================================================"
echo "Execução finalizada!"
echo "Verifique o arquivo de log e o relatório gerado na pasta reports/"
