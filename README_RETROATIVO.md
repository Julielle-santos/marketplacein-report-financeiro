# Relatório Financeiro Retroativo

Este documento explica como usar o script `financial_report_retroactive.py` para gerar relatórios financeiros com datas retroativas.

## Descrição

O script `financial_report_retroactive.py` foi criado para gerar relatórios financeiros como se tivessem sido executados em uma data específica no passado. Isso é útil para:

- Reprocessar relatórios de períodos anteriores
- Gerar relatórios históricos para análise
- Corrigir relatórios que falharam em execuções anteriores

## Diferenças do Script Original

### Script Original (`financial_report.py`)
- Usa a data atual como referência
- Busca o período de repasse vigente (`isCurrent: true`)
- Inclui todos os pedidos até a data atual

### Script Retroativo (`financial_report_retroactive.py`)
- Aceita uma data específica como parâmetro
- Busca o período de repasse válido para a data informada
- Filtra pedidos criados até a data de referência
- Usa `isCurrent: false` para consultar períodos históricos

## Como Usar

### Sintaxe Básica
```bash
python3 financial_report_retroactive.py --date DD/MM/YYYY
```

### Exemplo para 25/08/2025
```bash
python3 financial_report_retroactive.py --date 25/08/2025
```

### Usando o Script de Exemplo
```bash
./run_retroactive_example.sh
```

## Parâmetros

| Parâmetro | Descrição | Obrigatório | Formato | Exemplo |
|-----------|-----------|-------------|---------|---------|
| `--date` ou `-d` | Data de referência | Sim | DD/MM/YYYY | 25/08/2025 |

## Funcionalidades

### 1. Busca de Período de Repasse
- Procura o período de repasse que estava vigente na data informada
- Se não encontrar um período exato, busca o mais próximo anterior
- Valida se existe um período válido para a data

### 2. Filtragem de Registros
- Consulta registros do ciclo usando `isCurrent: false`
- Filtra apenas registros criados até a data de referência
- Mantém compatibilidade com múltiplos sellers/tenants

### 3. Geração de Arquivos
- **Log**: `logs/financial_report_retroactive_YYYYMMDD_HHMMSS.log`
- **Relatório**: `reports/marketplacein-relatorio_financeiro-retroativo-YYYYMMDD.xlsx`

### 4. Email
- Envia relatório com identificação de "Retroativo"
- Inclui data de referência no assunto e corpo do email
- Em caso de erro, envia log de erro para a equipe de TI

## Exemplos de Uso

### Caso 1: Relatório para 25/08/2025
```bash
python3 financial_report_retroactive.py --date 25/08/2025
```
**Resultado**: Gera relatório com pedidos até 25/08/2025

### Caso 2: Relatório para o final de julho
```bash
python3 financial_report_retroactive.py --date 31/07/2025
```
**Resultado**: Gera relatório com pedidos até 31/07/2025

### Caso 3: Usando formato curto do parâmetro
```bash
python3 financial_report_retroactive.py -d 15/06/2025
```
**Resultado**: Gera relatório com pedidos até 15/06/2025

## Validações

### Data Futura
- O script impede execução com datas futuras
- Exibe erro e termina a execução

### Formato de Data
- Aceita apenas formato DD/MM/YYYY
- Valida se a data é válida (ex: 31/02/2025 será rejeitada)

### Período de Repasse
- Verifica se existe um período de repasse válido para a data
- Se não encontrar, exibe erro detalhado

## Logs

O script gera logs detalhados incluindo:
- Data de referência utilizada
- Período de repasse encontrado
- Tenants e sellers processados
- Status de cada pedido processado
- Erros e warnings

### Exemplo de Log
```
2025-09-11 10:30:00 - INFO - Iniciando processamento retroativo de pedidos
2025-09-11 10:30:00 - INFO - Data de referência: 25/08/2025
2025-09-11 10:30:01 - INFO - Período encontrado: 2025-08-30T00:00:00.000Z
2025-09-11 10:30:02 - INFO - Tenants encontrados: 2
2025-09-11 10:30:02 - INFO - - Tenant: YSKY97446016589275 (Unicpharma) - 15 registros
2025-09-11 10:30:02 - INFO - - Tenant: YSKY67656203854813 (Unicdrogaria) - 3 registros
```

## Ambiente e Dependências

### Variáveis de Ambiente
O script usa as mesmas variáveis do script original:
- `API_TOKEN`
- `APPLICATION_ID` 
- `SELLER_ID`
- `BASE_URL`
- Configurações de email (SMTP_*)
- Destinatários (BUSINESS_RECIPIENTS, IT_RECIPIENTS)

### Dependências Python
- pandas
- requests
- openpyxl
- python-dotenv

## Troubleshooting

### Erro: "Nenhum período de repasse válido encontrado"
- **Causa**: Não existe período de repasse para a data informada
- **Solução**: Verificar se a data está correta ou se há períodos cadastrados

### Erro: "Formato de data inválido"
- **Causa**: Data não está no formato DD/MM/YYYY
- **Solução**: Usar formato correto (ex: 25/08/2025)

### Erro: "A data de referência não pode ser futura"
- **Causa**: Data informada é posterior à data atual
- **Solução**: Usar uma data no passado

### Nenhum pedido processado
- **Causa**: Não há pedidos para o período/data informada
- **Solução**: Verificar se existem pedidos para o período ou ajustar a data

## ⚠️ Limitação Técnica Importante

**Os relatórios retroativos podem apresentar pequenas divergências** (tipicamente 4-9 pedidos) em comparação com relatórios originais gerados na mesma data.

### Por que isso acontece?

1. **API retorna estado atual**: A API da Omnik sempre retorna o estado ATUAL dos dados, não o estado histórico
2. **Pedidos adicionados posteriormente**: Pedidos podem ser adicionados ao ciclo APÓS sua criação
3. **Sem consulta histórica**: Não há forma de consultar o estado exato do ciclo em uma data específica

### Exemplo prático:
- **Relatório original (23/08/2025)**: 172 pedidos ✅
- **Relatório retroativo (23/08/2025)**: 176 pedidos ⚠️ (+4 pedidos)
- **Diferença**: 4 pedidos que foram adicionados ao ciclo APÓS 23/08/2025

### Esta divergência é tecnicamente esperada e não indica erro no script.

## Notas Importantes

1. **Backup**: Sempre mantenha backup dos relatórios originais antes de reprocessar
2. **Performance**: Relatórios retroativos podem ser mais lentos devido à quantidade de dados
3. **Dados**: Os dados retroativos dependem da disponibilidade na API da Omnik
4. **Timezone**: Todas as datas são processadas no timezone UTC
5. **Múltiplos Sellers**: O script suporta múltiplos sellers/tenants automaticamente
6. **Divergências**: Pequenas diferenças (4-9 pedidos) são tecnicamente esperadas devido às limitações da API

## Suporte

Para dúvidas ou problemas:
1. Verifique os logs gerados
2. Confirme as configurações de ambiente
3. Teste com uma data recente primeiro
4. Entre em contato com a equipe de TI Digital
