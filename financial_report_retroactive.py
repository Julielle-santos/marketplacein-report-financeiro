"""
Script para gerar relatórios financeiros retroativos do marketplace.

Este script permite gerar relatórios para uma data específica no passado,
replicando o comportamento do script original para aquela data.

IMPORTANTE - LIMITAÇÃO TÉCNICA:
Os relatórios retroativos podem apresentar pequenas divergências (tipicamente 4-9 pedidos)
em comparação com relatórios originais gerados na mesma data. Isso ocorre porque:

1. A API da Omnik retorna sempre o estado ATUAL dos dados, não o estado histórico
2. Pedidos podem ser adicionados ou removidos do ciclo APÓS sua criação
3. Não há forma de consultar o estado exato do ciclo em uma data específica

Esta divergência é tecnicamente esperada e não indica erro no script.

Uso:
    python financial_report_retroactive.py --date DD/MM/YYYY

Exemplo:
    python financial_report_retroactive.py --date 25/08/2025
"""

import os
import json
import requests
import pandas as pd
import logging
import smtplib
import time
import sys
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configura o logging básico para stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def setup_logging(reference_date=None):
    """Configura o logging do script"""
    # Cria o diretório logs se não existir
    os.makedirs('logs', exist_ok=True)
    
    # Define a data para o nome do arquivo
    date_str = reference_date.strftime('%Y%m%d') if reference_date else datetime.now().strftime('%Y%m%d')
    timestamp = datetime.now().strftime('%H%M%S')
    
    # Configura o arquivo de log
    log_file = f"logs/financial_report_retroactive_{date_str}_{timestamp}.log"
    
    # Adiciona handler para arquivo
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    
    logging.info("=== Iniciando configuração do logging (modo retroativo) ===")
    logging.info(f"Arquivo de log: {log_file}")
    if reference_date:
        logging.info(f"Data de referência: {reference_date.strftime('%d/%m/%Y')}")
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

def get_transfer_period_by_date(reference_date):
    """Consulta o período de repasse válido para uma data específica"""
    logging.info(f"=== Consultando período de repasse para a data {reference_date.strftime('%d/%m/%Y')} ===")
    url = f"{BASE_URL}/v1/financial/cycle/available-transfers"
    params = {'typeOfCycle': 'MONTHLY'}
    
    response = make_request('GET', url, headers=HEADERS, params=params)
    data = response.json()
    
    # Procura o período que contém a data de referência
    target_period = None
    date_formats = ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d']
    
    for period in data:
        beginning_date = None
        end_date = None
        
        # Tenta diferentes formatos de data
        for fmt in date_formats:
            try:
                beginning_date = datetime.strptime(period['beginningOfCycle'], fmt)
                end_date = datetime.strptime(period['endOfCycle'], fmt)
                break
            except ValueError:
                continue
        
        if not beginning_date or not end_date:
            logging.warning(f"Não foi possível parsear as datas do período: {period}")
            continue
        
        # Verifica se a data de referência está dentro do período do ciclo
        if beginning_date.date() <= reference_date.date() <= end_date.date():
            target_period = period
            # Marca se é o período atual ou histórico baseado no flag isCurrent
            target_period['_is_current_period'] = period.get('isCurrent', False)
            
            period_type = "vigente atual" if period.get('isCurrent', False) else "histórico"
            logging.info(f"Período {period_type} encontrado: {period['transferDate']} (início: {beginning_date.strftime('%d/%m/%Y')}, fim: {end_date.strftime('%d/%m/%Y')})")
            break
    
    if not target_period:
        # Se não encontrar um período exato, procura o mais próximo anterior
        logging.warning(f"Nenhum período exato encontrado para {reference_date.strftime('%d/%m/%Y')}, procurando período mais próximo...")
        
        valid_periods = []
        for period in data:
            # Tenta diferentes formatos de data
            end_date = None
            for fmt in date_formats:
                try:
                    end_date = datetime.strptime(period['endOfCycle'], fmt)
                    break
                except ValueError:
                    continue
            
            if end_date and end_date.date() <= reference_date.date():
                valid_periods.append((period, end_date))
        
        if valid_periods:
            # Ordena por data de fim e pega o mais recente
            valid_periods.sort(key=lambda x: x[1], reverse=True)
            target_period = valid_periods[0][0]
            target_period['_is_current_period'] = False  # Marca para usar isCurrent=false
            logging.info(f"Período mais próximo encontrado: {target_period['transferDate']}")
        else:
            logging.error(f"Nenhum período de repasse válido encontrado para a data {reference_date.strftime('%d/%m/%Y')}")
            raise Exception(f"Nenhum período de repasse válido encontrado para a data {reference_date.strftime('%d/%m/%Y')}")
    
    logging.debug(f"Detalhes do período: {json.dumps(target_period, indent=2)}")
    return target_period

def get_cycle_registers(transfer_date, reference_date=None, is_current_period=False):
    """Consulta os registros do ciclo de repasse"""
    logging.info(f"=== Consultando registros do ciclo para a data {transfer_date} ===")
    if reference_date:
        logging.info(f"Data de referência: {reference_date.strftime('%d/%m/%Y')}")
    
    url = f"{BASE_URL}/v1/financial/cycle/registers"
    # Usa isCurrent baseado se é o período vigente ou histórico
    is_current_str = 'true' if is_current_period else 'false'
    logging.info(f"Usando isCurrent: {is_current_str} ({'período vigente' if is_current_period else 'período histórico'})")
    
    params = {
        'transferDate': transfer_date,
        'isCurrent': is_current_str
    }
    
    response = make_request('GET', url, headers=HEADERS, params=params)
    registers = response.json()
    
    # Para script retroativo, filtramos por createdDate para incluir apenas pedidos
    # que existiam na data de referência (replicando o cenário exato daquela data)
    if reference_date:
        filtered_registers = []
        for register in registers:
            # Verifica a data de criação do registro
            created_date_str = register.get('createDate', '')
            if created_date_str:
                created_date = None
                date_formats = ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d']
                
                for fmt in date_formats:
                    try:
                        created_date = datetime.strptime(created_date_str, fmt)
                        break
                    except ValueError:
                        continue
                
                # Inclui apenas pedidos criados ATÉ a data de referência (final do dia)
                reference_end_of_day = reference_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                if created_date and created_date <= reference_end_of_day:
                    filtered_registers.append(register)
                elif created_date:
                    # Debug: mostrar por que está sendo excluído
                    logging.debug(f"Excluindo pedido criado em {created_date} > {reference_end_of_day}")
                elif not created_date:
                    # Se não conseguir parsear a data, EXCLUI para ser mais conservador
                    logging.warning(f"Não foi possível parsear createdDate: {created_date_str}, EXCLUINDO registro")
            # else:
                # Se não tem data de criação, EXCLUI para ser mais conservador
        
        logging.info(f"Encontrados {len(registers)} registros no ciclo, {len(filtered_registers)} criados até {reference_date.strftime('%d/%m/%Y')}")
        registers = filtered_registers
    else:
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

def process_orders_retroactive(reference_date):
    """Processa os pedidos retroativamente para uma data específica"""
    log_file = setup_logging(reference_date)
    success = False
    
    try:
        logging.info("=== Iniciando processamento retroativo de pedidos ===")
        logging.info(f"Data de referência: {reference_date.strftime('%d/%m/%Y')}")
        
        # Obtém o ciclo para a data de referência
        cycle_info = get_transfer_period_by_date(reference_date)
        if not cycle_info:
            logging.error(f"Não foi possível obter informações do ciclo para a data {reference_date.strftime('%d/%m/%Y')}")
            return
        
        # Obtém os registros do ciclo até a data de referência
        is_current_period = cycle_info.get('_is_current_period', False)
        cycle_registers = get_cycle_registers(cycle_info['transferDate'], reference_date, is_current_period)
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
        
        # Aviso sobre limitação técnica
        logging.info("=== IMPORTANTE - LIMITAÇÃO TÉCNICA ===")
        logging.info("Este relatório retroativo pode apresentar pequenas divergências")
        logging.info("em relação ao relatório original gerado na mesma data.")
        logging.info("Isso ocorre porque a API retorna o estado ATUAL dos dados,")
        logging.info("não o estado que existia na data de referência.")
        logging.info("Divergências de 4-9 pedidos são tecnicamente esperadas.")
        
        if not orders_data:
            logging.warning("Nenhum pedido foi processado com sucesso")
            return
        
        # Gera o relatório Excel
        date_str = reference_date.strftime("%Y%m%d")
        output_file = f"reports/marketplacein-relatorio_financeiro-retroativo-{date_str}.xlsx"
        generate_excel_report(orders_data, output_file)
        
        # Envia email com o relatório
        subject = f"Relatório Financeiro Marketplace (Retroativo) - {reference_date.strftime('%d/%m/%Y')}"
        body = f"""
        Prezados,
        
        Segue em anexo o relatório financeiro retroativo do marketplace referente à data {reference_date.strftime('%d/%m/%Y')}.
        
        Data de referência: {reference_date.strftime('%d/%m/%Y')}
        Total de pedidos processados: {len(orders_data)}
        Total de sellers: {len(unique_tenants)}
        Sellers processados: {', '.join([f"{info['seller_name']} ({info['count']} pedidos)" for info in tenant_counts.values()])}
        
        IMPORTANTE: Relatórios retroativos podem apresentar pequenas divergências (4-9 pedidos) 
        em relação aos relatórios originais devido às limitações da API da Omnik.
        Esta diferença é tecnicamente esperada.
        
        Atenciosamente,
        TI Digital Rede d1000
        """
        
        send_email(BUSINESS_RECIPIENTS, subject, body, [output_file])
        success = True
        
        logging.info(f"Relatório retroativo gerado com sucesso para a data {reference_date.strftime('%d/%m/%Y')}")
        
    except Exception as e:
        logging.error(f"Erro ao processar pedidos retroativos: {str(e)}")
        logging.debug(f"Detalhes do erro: {str(e)}")
        
        # Envia email de erro para TI
        subject = f"ERRO - Relatório Financeiro Marketplace (Retroativo) - {reference_date.strftime('%d/%m/%Y')}"
        body = f"""
        Prezados,
        
        Ocorreu um erro durante a geração do relatório financeiro retroativo do marketplace.
        
        Data de referência: {reference_date.strftime('%d/%m/%Y')}
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
            logging.info("=== Processamento retroativo concluído com sucesso ===")
        else:
            logging.error("=== Processamento retroativo concluído com erro ===")

def main():
    """Função principal que processa os argumentos da linha de comando"""
    parser = argparse.ArgumentParser(description='Geração de relatório financeiro retroativo')
    parser.add_argument('--date', '-d', required=True, 
                       help='Data de referência no formato DD/MM/YYYY (ex: 25/08/2025)')
    
    args = parser.parse_args()
    
    try:
        # Converte a string da data para objeto datetime
        reference_date = datetime.strptime(args.date, '%d/%m/%Y')
        logging.info(f"=== Iniciando aplicação de relatório financeiro retroativo ===")
        logging.info(f"Data de referência: {reference_date.strftime('%d/%m/%Y')}")
        
        # Valida se a data não é futura
        if reference_date.date() > datetime.now().date():
            logging.error(f"A data de referência ({reference_date.strftime('%d/%m/%Y')}) não pode ser futura")
            sys.exit(1)
        
        # Processa os pedidos retroativamente
        process_orders_retroactive(reference_date)
        
    except ValueError as e:
        logging.error(f"Formato de data inválido. Use DD/MM/YYYY. Erro: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Erro na execução do script: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
