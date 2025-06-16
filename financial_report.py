import os
import json
import requests
import pandas as pd
import logging
import smtplib
import time
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configura o logging básico para stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def setup_logging():
    """Configura o logging do script"""
    # Cria o diretório logs se não existir
    os.makedirs('logs', exist_ok=True)
    
    # Configura o arquivo de log
    log_file = f"logs/financial_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Adiciona handler para arquivo
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    
    logging.info("=== Iniciando configuração do logging ===")
    logging.info(f"Arquivo de log: {log_file}")
    return log_file

# Carrega variáveis de ambiente
load_dotenv()
logging.info("Variáveis de ambiente carregadas")

# Configurações da API
API_TOKEN = os.getenv('API_TOKEN')
APPLICATION_ID = os.getenv('APPLICATION_ID')
SELLER_ID = os.getenv('SELLER_ID')
BASE_URL = os.getenv('BASE_URL', 'https://api.omnik.io')  # Usa valor do ConfigMap com fallback

# Configurações de email
SMTP_SERVER = os.getenv('SMTP_SERVER', 'mailerprofarma.ger.local')
SMTP_PORT = int(os.getenv('SMTP_PORT', '25'))
SMTP_USER = os.getenv('SMTP_USER', 'd1000.omni@mailerprofarma.com.br')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'TI Rede d1000 <d1000.ti.digital@mailerprofarma.com.br>')
BUSINESS_RECIPIENTS = os.getenv('BUSINESS_RECIPIENTS', '').split(',')
IT_RECIPIENTS = os.getenv('IT_RECIPIENTS', '').split(',')

# Configuração de retry para requests
def create_session_with_retry():
    """Cria uma sessão com configuração de retry"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,  # número total de tentativas
        backoff_factor=1,  # tempo de espera entre tentativas (1, 2, 4, 8, 16 segundos)
        status_forcelist=[429, 500, 502, 503, 504],  # códigos de erro para retry
        allowed_methods=["GET", "POST"]  # métodos HTTP permitidos para retry
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# Cria a sessão com retry
session = create_session_with_retry()

# Headers padrão para as requisições
HEADERS = {
    'token': API_TOKEN,
    'application_id': APPLICATION_ID,
    'seller': SELLER_ID,
    'Content-Type': 'application/json',
    'Host': 'api.omnik.io'
}

def make_request(method, url, **kwargs):
    """Faz uma requisição HTTP com retry e logging"""
    try:
        logging.info(f"Fazendo requisição {method} para {url}")
        logging.debug(f"Parâmetros da requisição: {kwargs}")
        
        response = session.request(method, url, **kwargs)
        response.raise_for_status()
        
        logging.info(f"Requisição {method} para {url} concluída com sucesso")
        logging.debug(f"Resposta: {response.text[:500]}...")  # Log dos primeiros 500 caracteres da resposta
        
        return response
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logging.warning(f"Rate limit atingido na requisição {method} para {url}. Aguardando antes de tentar novamente...")
            logging.debug(f"Detalhes do erro: {str(e)}")
            time.sleep(5)  # Espera adicional para rate limit
            return session.request(method, url, **kwargs)
        logging.error(f"Erro HTTP na requisição {method} para {url}: {str(e)}")
        logging.debug(f"Detalhes do erro: {e.response.text}")
        raise
    except Exception as e:
        logging.error(f"Erro inesperado na requisição {method} para {url}: {str(e)}")
        raise

def get_current_transfer_period():
    """Consulta o período de repasse vigente"""
    logging.info("=== Consultando período de repasse vigente ===")
    url = f"{BASE_URL}/v1/financial/cycle/available-transfers"
    params = {'typeOfCycle': 'MONTHLY'}
    
    response = make_request('GET', url, headers=HEADERS, params=params)
    data = response.json()
    current_period = next((item for item in data if item['isCurrent']), None)
    
    if not current_period:
        logging.error("Nenhum período de repasse vigente encontrado")
        raise Exception("Nenhum período de repasse vigente encontrado")
    
    logging.info(f"Período de repasse encontrado: {current_period['transferDate']}")
    logging.debug(f"Detalhes do período: {json.dumps(current_period, indent=2)}")
    return current_period

def get_cycle_registers(transfer_date):
    """Consulta os registros do ciclo de repasse"""
    logging.info(f"=== Consultando registros do ciclo para a data {transfer_date} ===")
    url = f"{BASE_URL}/v1/financial/cycle/registers"
    params = {
        'transferDate': transfer_date,
        'isCurrent': 'true'
    }
    
    response = make_request('GET', url, headers=HEADERS, params=params)
    registers = response.json()
    logging.info(f"Encontrados {len(registers)} registros no ciclo")
    logging.debug(f"Primeiros 3 registros: {json.dumps(registers[:3], indent=2)}")
    return registers

def get_order_details(marketplace_id, tenant):
    """Consulta os detalhes do pedido"""
    logging.info(f"=== Consultando detalhes do pedido {marketplace_id} (tenant: {tenant}) ===")
    url = f"{BASE_URL}/HUB/v1/orders/marketplaceid/{marketplace_id}"
    
    # Cria headers específicos para este tenant
    headers = {**HEADERS, 'seller': tenant}
    
    response = make_request('GET', url, headers=headers)
    order_details = response.json()
    logging.info(f"Detalhes do pedido {marketplace_id} obtidos com sucesso")
    logging.debug(f"Detalhes do pedido: {json.dumps(order_details, indent=2)}")
    return order_details

def get_order_financial_details(marketplace_id, tenant):
    """Consulta os detalhes financeiros do pedido"""
    logging.info(f"=== Consultando detalhes financeiros do pedido {marketplace_id} ===")
    url = f"{BASE_URL}/v1/financial/register/order-financial-detail/{marketplace_id}"
    headers = {**HEADERS, 'tenant': tenant}
    
    response = make_request('GET', url, headers=headers)
    financial_details = response.json()
    logging.info(f"Detalhes financeiros do pedido {marketplace_id} obtidos com sucesso")
    logging.debug(f"Detalhes financeiros: {json.dumps(financial_details, indent=2)}")
    return financial_details

def calculate_order_total(items):
    """Calcula o total do pedido baseado nos itens"""
    total = 0
    for item in items:
        quantity = item['quantityData']['quantity']
        unit_price = item['priceData']['unitPrice']
        discount = item['priceData']['discountUnit']
        item_total = quantity * (unit_price - discount)
        total += item_total
        print(f"Item: {item['skuData']['skuName']} - Quantidade: {quantity}, Preço: {unit_price}, Desconto: {discount}, Total: {item_total}")
    return total

def calculate_freight_total(items):
    """Calcula o total do frete baseado nos itens"""
    total = 0
    for item in items:
        freight = item['freightData']['chargedValue']
        total += freight
        print(f"Frete do item {item['skuData']['skuName']}: {freight}")
    return total

def format_payment_method(payment):
    """Formata o método de pagamento"""
    payment_type = payment.get('type', '')
    card = payment.get('card', '')
    plots = payment.get('amountPlots', '')
    return f"{payment_type} {card} {plots}x"

def send_to_teams(df):
    """Envia os dados do relatório para o webhook do Teams"""
    try:
        print("\n=== Iniciando envio do relatório para o Teams ===")
        print(f"URL do webhook: {TEAMS_WEBHOOK_URL}")
        
        # Formata os dados para o Teams
        print("Formatando dados para o Teams...")
        table_data = []
        for _, row in df.iterrows():
            table_data.append({
                "ID do Pedido": str(row['ID do Pedido']),
                "Pedido VTEX": str(row['Pedido VTEX']),
                "Código do Seller": str(row['Código do Seller']),
                "Data de criação do pedido": str(row['Data de criação do pedido']),
                "Data de entrega do pedido": str(row['Data de entrega do pedido']),
                "Data de aprovação do pedido": str(row['Data de aprovação do pedido']),
                "Conciliação/Frequência de repasse": str(row['Conciliação/Frequência de repasse']),
                "Total do pedido": f"R$ {row['Total do pedido']:.2f}",
                "Total dos produtos": f"R$ {row['Total dos produtos']:.2f}",
                "Total do frete": f"R$ {row['Total do frete']:.2f}",
                "Comissão Produto (%)": f"{row['Comissão Produto (%)']:.2f}%",
                "Comissão Frete (%)": f"{row['Comissão Frete (%)']:.2f}%",
                "Meio de pagamento": str(row['Meio de pagamento']),
                "Comissão Total": f"R$ {row['Comissão Total']:.2f}",
                "Comissão Produto": f"R$ {row['Comissão Produto']:.2f}",
                "Comissão Frete": f"R$ {row['Comissão Frete']:.2f}",
                "Total repasse": f"R$ {row['Total repasse']:.2f}",
                "Valor Produtos - Comissão Produto": f"R$ {row['Valor Produtos - Comissão Produto']:.2f}",
                "Valor Frete - Comissão Frete": f"R$ {row['Valor Frete - Comissão Frete']:.2f}"
            })
            
            # Adiciona campos de campanha se existirem
            if 'Campanha' in row:
                table_data[-1].update({
                    "Campanha": str(row['Campanha']),
                    "Data de início da campanha": str(row['Data de início da campanha']),
                    "Data de fim da campanha": str(row['Data de fim da campanha']),
                    "Descrição da campanha": str(row['Descrição da campanha'])
                })
                
        print(f"Dados formatados para {len(table_data)} pedidos")
        
        # Cria a mensagem para o Teams
        print("Criando mensagem para o Teams...")
        
        # Cria o cabeçalho da tabela
        headers = [
            "ID do Pedido", "Pedido VTEX", "Código do Seller",
            "Data de criação", "Data de entrega", "Data de aprovação",
            "Conciliação", "Total pedido", "Total produtos", "Total frete",
            "Comissão Produto (%)", "Comissão Frete (%)", "Meio de pagamento",
            "Comissão Total", "Comissão Produto", "Comissão Frete",
            "Total repasse", "Valor Produtos - Comissão", "Valor Frete - Comissão"
        ]
        
        # Adiciona campos de campanha se existirem
        if 'Campanha' in table_data[0]:
            headers.extend(["Campanha", "Início Campanha", "Fim Campanha", "Descrição Campanha"])
        
        table_header = "| " + " | ".join(headers) + " |"
        table_separator = "|" + "|".join(["---" for _ in range(len(headers))]) + "|"
        
        # Cria as linhas da tabela
        table_rows = []
        for item in table_data:
            row_values = [
                item['ID do Pedido'],
                item['Pedido VTEX'],
                item['Código do Seller'],
                item['Data de criação do pedido'],
                item['Data de entrega do pedido'],
                item['Data de aprovação do pedido'],
                item['Conciliação/Frequência de repasse'],
                item['Total do pedido'],
                item['Total dos produtos'],
                item['Total do frete'],
                item['Comissão Produto (%)'],
                item['Comissão Frete (%)'],
                item['Meio de pagamento'],
                item['Comissão Total'],
                item['Comissão Produto'],
                item['Comissão Frete'],
                item['Total repasse'],
                item['Valor Produtos - Comissão Produto'],
                item['Valor Frete - Comissão Frete']
            ]
            
            # Adiciona campos de campanha se existirem
            if 'Campanha' in item:
                row_values.extend([
                    item['Campanha'],
                    item['Data de início da campanha'],
                    item['Data de fim da campanha'],
                    item['Descrição da campanha']
                ])
            
            row = "| " + " | ".join(row_values) + " |"
            table_rows.append(row)
        
        # Monta a tabela completa
        table = "\n".join([table_header, table_separator] + table_rows)
        
        # Cria a mensagem final
        message = {
            "text": f"# Relatório Financeiro - {datetime.now().strftime('%d/%m/%Y')}\n\n{table}"
        }
        
        print("Mensagem criada com sucesso")
        
        # Envia para o webhook do Teams
        print("Enviando mensagem para o webhook do Teams...")
        print(f"Tamanho da mensagem: {len(str(message))} bytes")
        
        response = requests.post(TEAMS_WEBHOOK_URL, json=message)
        print(f"Status code da resposta: {response.status_code}")
        print(f"Resposta do servidor: {response.text}")
        
        response.raise_for_status()
        print("Relatório enviado com sucesso para o Teams")
        
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem para o Teams: {str(e)}")
        if hasattr(e.response, 'text'):
            print(f"Detalhes do erro: {e.response.text}")
        raise
    except Exception as e:
        print(f"Erro inesperado ao enviar mensagem para o Teams: {str(e)}")
        raise

def process_order_data(order_data, financial_data, cycle_data, cycle_registers):
    """Processa os dados do pedido e retorna um dicionário com os campos formatados"""
    try:
        logging.info("=== Processando dados do pedido ===")
        
        # Extrai dados do pedido
        order_id = order_data.get('orderData', {}).get('id', '')
        marketplace_id = order_data.get('marketplaceData', {}).get('marketPlaceId', '')
        logging.info(f"Processando pedido {order_id} (marketplace: {marketplace_id})")
        
        # Obtém sellerName e tenant dos registros do ciclo
        seller_name = ''
        tenant = ''
        for register in cycle_registers:
            if register.get('marketplaceId') == marketplace_id and register.get('type') == 'SALE':
                seller_name = register.get('sellerName', '')
                tenant = register.get('tenant', '')
                logging.info(f"Seller encontrado: {seller_name} (tenant: {tenant})")
                break
        
        order_status = order_data.get('orderData', {}).get('status', '')
        create_date = order_data.get('createDate', '')
        delivery_date = order_data.get('deliveryData', {}).get('deliveryDate', '')
        approval_date = order_data.get('orderData', {}).get('approvalDate', '')
        
        # Extrai dados financeiros
        financial_cycle_type = financial_data.get('financialCicleType', '')
        beginning_of_cycle = cycle_data.get('beginningOfCycle', '')
        end_of_cycle = cycle_data.get('endOfCycle', '')
        total_order_value = order_data.get('orderValuesData', {}).get('value', 0.0)
        
        # Calcula valor total dos produtos
        total_products = 0.0
        for item in order_data.get('items', []):
            quantity = item.get('quantityData', {}).get('quantity', 0)
            unit_price = item.get('priceData', {}).get('unitPrice', 0.0)
            discount = item.get('priceData', {}).get('discountUnit', 0.0)
            total_products += quantity * (unit_price - discount)
        
        # Calcula valor total do frete
        total_freight = sum(item.get('freightData', {}).get('chargedValue', 0.0) for item in order_data.get('items', []))
        
        # Extrai percentuais de comissão
        product_commission_percent = financial_data.get('itensCommissionPercent', 0.0)
        freight_commission_percent = financial_data.get('freightCommissionPercent', 0.0)
        
        # Extrai dados de pagamento
        payment_type = ''
        payment_card = ''
        payment_plots = ''
        for payment in order_data.get('paymentData', {}).get('formsPayments', []):
            payment_type = payment.get('type', '')
            payment_card = payment.get('card', '')
            payment_plots = payment.get('amountPlots', '')
            break
        
        payment_info = f"{payment_type} {payment_card} {payment_plots}x"
        
        # Extrai valores de comissão
        total_commission = financial_data.get('totalCommissionValue', 0.0)
        product_commission = financial_data.get('itensCommissionValue', 0.0)
        freight_commission = financial_data.get('freightCommissionValue', 0.0)
        total_transfer = financial_data.get('totalTransferSeller', 0.0)
        
        # Calcula valores de repasse
        product_transfer = total_products - product_commission
        freight_transfer = total_freight - freight_commission
        
        # Extrai dados de campanha
        campaign_id = ''
        campaign_initial_date = ''
        campaign_final_date = ''
        campaign_description = ''
        
        for discount in financial_data.get('discounts', []):
            campaign_id = discount.get('promotionId', '')
            break
            
        for campaign in order_data.get('campaigns', []):
            campaign_initial_date = campaign.get('initialDate', '')
            campaign_final_date = campaign.get('finalDate', '')
            campaign_description = campaign.get('description', '')
            break
        
        campaign_vigency = f"{campaign_initial_date} - {campaign_final_date}" if campaign_initial_date and campaign_final_date else ''
        
        logging.info(f"Processamento do pedido {order_id} concluído com sucesso")
        return {
            'ID do Pedido': order_id,
            'Pedido VTEX': marketplace_id,
            'Código do Seller': tenant,
            'Nome do Seller': seller_name,
            'Status Pedido': order_status,
            'Data de criação do pedido': create_date,
            'Data de entrega do pedido': delivery_date,
            'Data de aprovação do pedido': approval_date,
            'Conciliação/Frequência de repasse': financial_cycle_type,
            'Início Ciclo': beginning_of_cycle,
            'Fim Ciclo': end_of_cycle,
            'Total do pedido': total_order_value,
            'Total dos produtos': total_products,
            'Total do frete': total_freight,
            'Comissão Produto (%)': product_commission_percent,
            'Comissão Frete (%)': freight_commission_percent,
            'Meio de pagamento': payment_info,
            'Comissão Total': total_commission,
            'Comissão Produto': product_commission,
            'Comissão Frete': freight_commission,
            'Total repasse': total_transfer,
            'Repasse Produto': product_transfer,
            'Repasse Frete': freight_transfer,
            'Campanha': campaign_id,
            'Vigência': campaign_vigency,
            'Descrição da campanha': campaign_description
        }
    except Exception as e:
        logging.error(f"Erro ao processar dados do pedido {order_id}: {str(e)}")
        logging.debug(f"Dados do pedido: {json.dumps(order_data, indent=2)}")
        logging.debug(f"Dados financeiros: {json.dumps(financial_data, indent=2)}")
        raise

def generate_excel_report(orders_data, output_file):
    """Gera o relatório em Excel com os dados processados"""
    try:
        logging.info("=== Gerando relatório Excel ===")
        logging.info(f"Total de pedidos a processar: {len(orders_data)}")
        
        # Cria o diretório reports se não existir
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Cria um DataFrame com os dados
        df = pd.DataFrame(orders_data)
        logging.info(f"DataFrame criado com {len(df)} linhas e {len(df.columns)} colunas")
        
        # Define a ordem das colunas conforme o arquivo de exemplo
        columns_order = [
            'ID do Pedido',
            'Pedido VTEX',
            'Código do Seller',
            'Nome do Seller',
            'Status Pedido',
            'Data de criação do pedido',
            'Data de entrega do pedido',
            'Data de aprovação do pedido',
            'Conciliação/Frequência de repasse',
            'Início Ciclo',
            'Fim Ciclo',
            'Total do pedido',
            'Total dos produtos',
            'Total do frete',
            'Comissão Produto (%)',
            'Comissão Frete (%)',
            'Meio de pagamento',
            'Comissão Total',
            'Comissão Produto',
            'Comissão Frete',
            'Total repasse',
            'Repasse Produto',
            'Repasse Frete',
            'Campanha',
            'Vigência',
            'Descrição da campanha'
        ]
        
        # Garante que todas as colunas existam no DataFrame
        for col in columns_order:
            if col not in df.columns:
                df[col] = ''
        
        # Reordena as colunas
        df = df[columns_order]
        
        # Formata as colunas numéricas
        numeric_columns = [
            'Total do pedido',
            'Total dos produtos',
            'Total do frete',
            'Comissão Produto (%)',
            'Comissão Frete (%)',
            'Comissão Total',
            'Comissão Produto',
            'Comissão Frete',
            'Total repasse',
            'Repasse Produto',
            'Repasse Frete'
        ]
        
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notnull(x) else '')
        
        # Formata as datas
        date_columns = [
            'Data de criação do pedido',
            'Data de entrega do pedido',
            'Data de aprovação do pedido',
            'Início Ciclo',
            'Fim Ciclo'
        ]
        
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].dt.strftime('%d/%m/%Y %H:%M:%S')
        
        # Salva o arquivo Excel
        df.to_excel(output_file, index=False, sheet_name='Relatório Financeiro')
        
        # Ajusta a largura das colunas
        with pd.ExcelWriter(output_file, engine='openpyxl', mode='a') as writer:
            worksheet = writer.sheets['Relatório Financeiro']
            for idx, col in enumerate(df.columns):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(col)
                )
                worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2
        
        logging.info(f"Relatório Excel gerado com sucesso: {output_file}")
        return df
        
    except Exception as e:
        logging.error(f"Erro ao gerar relatório Excel: {str(e)}")
        logging.debug(f"Dados do DataFrame: {df.head().to_dict()}")
        raise

def send_teams_notification(webhook_url, orders_data, cycle_info):
    """Envia notificação para o Teams com os dados processados"""
    try:
        # Cria o DataFrame
        df = pd.DataFrame(orders_data)
        
        # Formata os valores numéricos
        numeric_columns = [
            'Total do pedido', 'Total dos produtos', 'Total do frete',
            'Comissão Produto (%)', 'Comissão Frete (%)', 'Comissão Total',
            'Comissão Produto', 'Comissão Frete', 'Total repasse',
            'Repasse Produto', 'Repasse Frete'
        ]
        
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].apply(lambda x: f"R$ {x:.2f}".replace('.', ',') if pd.notnull(x) else 'R$ 0,00')
        
        # Formata as datas
        date_columns = [
            'Data de criação do pedido', 'Data de entrega do pedido',
            'Data de aprovação do pedido', 'Início Ciclo', 'Fim Ciclo'
        ]
        
        for col in date_columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            df[col] = df[col].dt.strftime('%d/%m/%Y %H:%M:%S')
        
        # Cria a tabela HTML
        html_table = df.to_html(index=False, classes='table table-striped')
        
        # Cria o payload do Teams
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "text": "Relatório Financeiro - Marketplace"
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Período: {cycle_info['beginningOfCycle']} até {cycle_info['endOfCycle']}",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Data de transferência: {cycle_info['transferDate']}",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Total de pedidos: {len(orders_data)}",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Total de comissão: {df['Comissão Total'].sum()}",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Total de repasse: {df['Total repasse'].sum()}",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": "Detalhamento dos pedidos:",
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": html_table,
                                "wrap": True
                            }
                        ],
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.0"
                    }
                }
            ]
        }
        
        # Envia a notificação
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        
        print("Notificação enviada com sucesso para o Teams")
        
    except Exception as e:
        print(f"Erro ao enviar notificação para o Teams: {str(e)}")
        raise

def send_email(recipients, subject, body, attachments=None, is_error=False):
    """Envia email com o relatório em anexo"""
    try:
        logging.info("=== Enviando email ===")
        logging.info(f"Destinatários: {', '.join(recipients)}")
        logging.info(f"Assunto: {subject}")
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        
        # Adiciona o corpo do email
        msg.attach(MIMEText(body, 'plain'))
        
        # Adiciona os anexos
        if attachments:
            for file_path in attachments:
                logging.info(f"Adicionando anexo: {file_path}")
                with open(file_path, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                    msg.attach(part)
        
        # Conecta ao servidor SMTP e envia o email
        logging.info(f"Conectando ao servidor SMTP: {SMTP_SERVER}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.send_message(msg)
            
        logging.info(f"Email enviado com sucesso para {', '.join(recipients)}")
        
    except Exception as e:
        logging.error(f"Erro ao enviar email: {str(e)}")
        logging.debug(f"Detalhes do erro: {str(e)}")
        raise

def process_orders():
    """Processa os pedidos e gera o relatório"""
    log_file = setup_logging()
    success = False
    
    try:
        logging.info("=== Iniciando processamento de pedidos ===")
        
        # Obtém o ciclo atual
        cycle_info = get_current_transfer_period()
        if not cycle_info:
            logging.error("Não foi possível obter informações do ciclo atual")
            return
        
        # Obtém os registros do ciclo
        cycle_registers = get_cycle_registers(cycle_info['transferDate'])
        if not cycle_registers:
            logging.error("Não foi possível obter os registros do ciclo")
            return
        
        # Filtra apenas os registros do tipo SALE
        sale_registers = [reg for reg in cycle_registers if reg.get('type') == 'SALE']
        logging.info(f"Total de registros de venda encontrados: {len(sale_registers)}")
        
        # Identifica e loga os diferentes tenants encontrados
        unique_tenants = set()
        tenant_counts = {}
        for register in sale_registers:
            tenant = register.get('tenant', '')
            seller_name = register.get('sellerName', '')
            if tenant:
                unique_tenants.add(tenant)
                if tenant not in tenant_counts:
                    tenant_counts[tenant] = {'count': 0, 'seller_name': seller_name}
                tenant_counts[tenant]['count'] += 1
        
        logging.info(f"Tenants encontrados: {len(unique_tenants)}")
        for tenant, info in tenant_counts.items():
            logging.info(f"  - Tenant: {tenant} ({info['seller_name']}) - {info['count']} registros")
        
        # Processa cada pedido
        orders_data = []
        processed_orders = set()  # Para evitar duplicatas
        
        for i, register in enumerate(sale_registers, 1):
            marketplace_id = register.get('marketplaceId')
            tenant = register.get('tenant', '')
            
            if not marketplace_id:
                logging.warning(f"Registro {i} não possui marketplaceId, pulando...")
                continue
                
            if not tenant:
                logging.warning(f"Registro {i} não possui tenant, pulando pedido {marketplace_id}...")
                continue
            
            # Evita processar o mesmo pedido múltiplas vezes
            order_key = f"{marketplace_id}_{tenant}"
            if order_key in processed_orders:
                logging.debug(f"Pedido {marketplace_id} do tenant {tenant} já processado, pulando...")
                continue
            
            processed_orders.add(order_key)
            # Calcula total de pedidos únicos para o logging
            total_unique_orders = len(set(f"{r.get('marketplaceId')}_{r.get('tenant')}" 
                                        for r in sale_registers 
                                        if r.get('marketplaceId') and r.get('tenant')))
            logging.info(f"Processando pedido {len(processed_orders)} de {total_unique_orders}: {marketplace_id} (tenant: {tenant})")
            
            try:
                # Obtém detalhes do pedido
                order_data = get_order_details(marketplace_id, tenant)
                if not order_data:
                    logging.warning(f"Não foi possível obter detalhes do pedido {marketplace_id}, pulando...")
                    continue
                    
                # Obtém detalhes financeiros do pedido
                financial_data = get_order_financial_details(marketplace_id, tenant)
                if not financial_data:
                    logging.warning(f"Não foi possível obter detalhes financeiros do pedido {marketplace_id}, pulando...")
                    continue
                
                # Processa os dados do pedido
                order_info = process_order_data(order_data, financial_data, cycle_info, cycle_registers)
                orders_data.append(order_info)
                logging.info(f"Pedido {marketplace_id} processado com sucesso")
                
            except Exception as e:
                logging.error(f"Erro ao processar pedido {marketplace_id} do tenant {tenant}: {str(e)}")
                logging.debug(f"Detalhes do erro: {str(e)}")
                # Continua processando os outros pedidos mesmo se um falhar
                continue
        
        logging.info(f"Total de pedidos processados com sucesso: {len(orders_data)}")
        logging.info(f"Total de tenants processados: {len(unique_tenants)}")
        
        if not orders_data:
            logging.warning("Nenhum pedido foi processado com sucesso")
            return
        
        # Gera o relatório Excel
        current_date = datetime.now().strftime("%Y%m%d")
        output_file = f"reports/marketplacein-relatorio_financeiro-{current_date}.xlsx"
        generate_excel_report(orders_data, output_file)
        
        # Envia email com o relatório
        subject = f"Relatório Financeiro Marketplace - {current_date}"
        body = f"""
        Prezados,
        
        Segue em anexo o relatório financeiro do marketplace referente à data {current_date}.
        
        Total de pedidos processados: {len(orders_data)}
        Total de sellers: {len(unique_tenants)}
        Sellers processados: {', '.join([f"{info['seller_name']} ({info['count']} pedidos)" for info in tenant_counts.values()])}
        
        Atenciosamente,
        TI Digital Rede d1000
        """
        
        send_email(BUSINESS_RECIPIENTS, subject, body, [output_file])
        success = True
        
    except Exception as e:
        logging.error(f"Erro ao processar pedidos: {str(e)}")
        logging.debug(f"Detalhes do erro: {str(e)}")
        
        # Envia email de erro para TI
        subject = f"ERRO - Relatório Financeiro Marketplace - {datetime.now().strftime('%Y%m%d')}"
        body = f"""
        Prezados,
        
        Ocorreu um erro durante a geração do relatório financeiro do marketplace.
        
        Detalhes do erro:
        {str(e)}
        
        O log completo está em anexo.
        
        Atenciosamente,
        TI Digital Rede d1000
        """
        
        send_email(IT_RECIPIENTS, subject, body, [log_file], is_error=True)
        raise
    
    finally:
        if success:
            logging.info("=== Processamento concluído com sucesso ===")
        else:
            logging.error("=== Processamento concluído com erro ===")

if __name__ == "__main__":
    logging.info("=== Iniciando aplicação de relatório financeiro ===")
    process_orders() 