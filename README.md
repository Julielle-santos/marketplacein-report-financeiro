# Relatório Financeiro de Pedidos

Esta aplicação automatiza a consulta de dados financeiros de pedidos e gera um relatório em Excel diariamente.

## Requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)

## Instalação

1. Clone este repositório
2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:
```
API_TOKEN=seu_token_aqui
APPLICATION_ID=seu_application_id_aqui
SELLER_ID=seu_seller_id_aqui
```

## Uso

Execute o script principal:
```bash
python financial_report.py
```

O script irá:
1. Executar imediatamente na primeira vez
2. Gerar um relatório Excel com o nome `relatorio_financeiro_YYYYMMDD.xlsx`
3. Agendar execuções diárias às 00:00

## Estrutura do Relatório

O relatório Excel contém as seguintes colunas:
- ID do Pedido
- Pedido VTEX
- Código do Seller
- Data de criação do pedido
- Data de entrega do pedido
- Data de aprovação do pedido
- Conciliação/Frequência de repasse
- Total do pedido
- Total dos produtos
- Total do frete
- Comissão Produto (%)
- Comissão Frete (%)
- Meio de pagamento
- Comissão Total
- Comissão Produto
- Comissão Frete
- Total repasse
- Valor Produtos - Comissão Produto
- Valor Frete - Comissão Frete
- Campanha (quando aplicável)
- Data de início da campanha (quando aplicável)
- Data de fim da campanha (quando aplicável)
- Descrição da campanha (quando aplicável)

## Manutenção

O script deve ser mantido em execução para gerar os relatórios diariamente. Recomenda-se:
1. Executar em um servidor
2. Usar um gerenciador de processos como PM2 ou Supervisor
3. Configurar logs para monitoramento 