# Financial Report - Marketplace In

Aplicação para geração automatizada de relatórios financeiros de pedidos do Marketplace In (d1000).

## 📋 Descrição

Esta aplicação consulta a API do Omnik para obter dados financeiros dos pedidos do marketplace e gera um relatório consolidado em Excel. O relatório é enviado por email para os stakeholders do negócio.

## 🏗️ Arquitetura

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   CronJob K8s   │ ───▶ │  financial_     │ ───▶ │   API Omnik     │
│   (8h diário)   │      │  report.py      │      │                 │
└─────────────────┘      └────────┬────────┘      └─────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
           ┌─────────────────┐         ┌─────────────────┐
           │  Excel Report   │         │   Email SMTP    │
           │  (.xlsx)        │         │                 │
           └─────────────────┘         └─────────────────┘
```

## 🔄 Fluxo de Execução

1. **Consulta período de repasse vigente**: Obtém o ciclo financeiro atual (mensal)
2. **Obtém registros do ciclo**: Lista todos os pedidos do ciclo de repasse
3. **Processa cada pedido**:
   - Consulta detalhes do pedido (`/HUB/v1/orders/marketplaceid/{orderId}`)
   - Consulta dados financeiros (`/v1/financial/register/order-financial-detail/{orderId}`)
4. **Gera relatório Excel**: Consolida todos os dados em uma planilha formatada
5. **Envia por email**: Dispara o relatório para os destinatários configurados

## 📊 Estrutura do Relatório

O relatório Excel contém as seguintes colunas:

| Coluna | Descrição |
|--------|-----------|
| ID do Pedido | Identificador interno do pedido |
| Pedido VTEX | ID do pedido no marketplace |
| **Bandeira** | Hostname do marketplace (ex: drogasmil, rosario) |
| Código do Seller | Identificador do seller |
| Nome do Seller | Nome do seller |
| Status Pedido | Status atual do pedido |
| Data de criação do pedido | Data/hora de criação |
| Data de entrega do pedido | Data/hora de entrega |
| Data de aprovação do pedido | Data/hora de aprovação |
| Conciliação/Frequência de repasse | Tipo de ciclo financeiro |
| Início Ciclo | Data de início do ciclo |
| Fim Ciclo | Data de fim do ciclo |
| Total do pedido | Valor total do pedido |
| Total dos produtos | Valor total dos produtos |
| Total do frete | Valor total do frete |
| Comissão Produto (%) | Percentual de comissão sobre produtos |
| Comissão Frete (%) | Percentual de comissão sobre frete |
| Meio de pagamento | Forma de pagamento utilizada |
| Comissão Total | Valor total de comissão |
| Comissão Produto | Valor de comissão sobre produtos |
| Comissão Frete | Valor de comissão sobre frete |
| Total repasse | Valor total a repassar ao seller |
| Repasse Produto | Valor de repasse referente a produtos |
| Repasse Frete | Valor de repasse referente a frete |
| Campanha | ID da campanha promocional (se houver) |
| Vigência | Período de vigência da campanha |
| Descrição da campanha | Descrição da campanha |

## ⚙️ Variáveis de Ambiente

### API Omnik
| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `API_TOKEN` | Token de autenticação da API | Sim |
| `APPLICATION_ID` | ID da aplicação | Sim |
| `SELLER_ID` | ID do seller padrão | Sim |
| `BASE_URL` | URL base da API (default: `https://api.omnik.io`) | Não |

### Email SMTP
| Variável | Descrição | Default |
|----------|-----------|---------|
| `SMTP_SERVER` | Servidor SMTP | `mailerprofarma.ger.local` |
| `SMTP_PORT` | Porta SMTP | `25` |
| `SMTP_USER` | Usuário SMTP | `d1000.omni@mailerprofarma.com.br` |
| `SMTP_PASSWORD` | Senha SMTP | - |
| `EMAIL_FROM` | Remetente do email | `TI Rede d1000 <d1000.ti.digital@mailerprofarma.com.br>` |
| `BUSINESS_RECIPIENTS` | Destinatários de negócio (separados por vírgula) | - |
| `IT_RECIPIENTS` | Destinatários de TI para erros (separados por vírgula) | - |

## 🚀 Deploy

### Requisitos
- Python 3.13+
- Docker
- Kubernetes

### Build da Imagem Docker

```bash
# Build para arquitetura amd64 (clusters Linux)
docker buildx build --platform linux/amd64 -t prdbrscadastroacr01.azurecr.io/marketplacein/financial-report:1.0.25 --push .
```

### Deploy no Kubernetes

```bash
# Aplicar ConfigMap e Secrets
kubectl apply -f k8s/config.yaml
kubectl apply -f k8s/secret.yaml

# Aplicar PVs e PVCs
kubectl apply -f k8s/pv.yaml
kubectl apply -f k8s/pvc.yaml

# Aplicar CronJob (execução diária às 23:55)
kubectl apply -f k8s/cronjob.yaml

# Aplicar CronJob de limpeza (arquivos > 30 dias)
kubectl apply -f k8s/cleanup-cronjob.yaml
```

### Teste Manual

```bash
# Executar job de teste
kubectl apply -f k8s/test-job.yaml

# Verificar logs
kubectl logs -f job/financial-report-test -n marketplace
```

## 📁 Estrutura do Projeto

```
├── financial_report.py          # Script principal
├── financial_report_retroactive.py  # Script para relatórios retroativos
├── Dockerfile                   # Definição da imagem Docker
├── requirements.txt             # Dependências Python
├── .env                         # Variáveis de ambiente (local)
├── k8s/                         # Manifests Kubernetes
│   ├── config.yaml              # ConfigMap
│   ├── secret.yaml              # Secrets
│   ├── pv.yaml                  # PersistentVolume
│   ├── pvc.yaml                 # PersistentVolumeClaim
│   ├── cronjob.yaml             # CronJob principal
│   ├── cleanup-cronjob.yaml     # CronJob de limpeza
│   ├── deployment.yaml          # Deployment (opcional)
│   └── test-job.yaml            # Job para testes
├── reports/                     # Relatórios gerados
├── logs/                        # Logs de execução
└── docs/                        # Documentação adicional
```

## 🔧 Desenvolvimento Local

```bash
# Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais

# Executar
python financial_report.py
```

## 📝 Logs

Os logs são salvos em `logs/financial_report_YYYYMMDD_HHMMSS.log` e contêm:
- Início e fim de cada etapa
- Detalhes dos pedidos processados
- Erros e exceções

## 🔒 Segurança

- Credenciais são armazenadas em Kubernetes Secrets
- Tokens de API não são logados
- Comunicação com API via HTTPS

## 📌 Versão Atual

**v1.0.25** - Dezembro 2024

### Changelog
- Adicionado campo "Bandeira" (marketplaceData.hostname) no relatório
- Corrigido bug no ajuste de largura das colunas do Excel
- Atualizado registry para Azure Container Registry
