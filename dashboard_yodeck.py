# dashboard_yodeck_mejorado.py
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, callback, no_update, ALL, callback_context
import dash_bootstrap_components as dbc
from datetime import datetime, timedelta
import re
import os
import glob
import numpy as np
import base64
import io
import json
import random
import shutil
from collections import defaultdict
import subprocess
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.units import inch

# --------------------------
# 1️⃣ Configuración inicial
# --------------------------
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# Precio fijo por cliente al mes
PRECIO_POR_CLIENTE = 15000

# Archivo para guardar la configuración de clientes
CONFIG_FILE = 'clientes_config.json'

# Carpeta para testigos
TESTIGOS_FOLDER = 'testigos'
os.makedirs(TESTIGOS_FOLDER, exist_ok=True)

# Carpeta para CSV con fecha
CSV_FOLDER = 'csv'
os.makedirs(CSV_FOLDER, exist_ok=True)

# Carpeta para contratos
CONTRATOS_FOLDER = 'contratos'
os.makedirs(CONTRATOS_FOLDER, exist_ok=True)

# --------------------------
# 2️⃣ Funciones para gestión de configuración
# --------------------------
def cargar_configuracion():
    """Cargar configuración de clientes desde archivo JSON"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_configuracion(config):
    """Guardar configuración de clientes en archivo JSON"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def obtener_nombres_reales():
    """Obtener diccionario de nombres reales desde configuración"""
    config = cargar_configuracion()
    return {k: v['nombre_real'] for k, v in config.items() if 'nombre_real' in v}

def obtener_info_cliente(cliente_id):
    """Obtener información completa de un cliente"""
    config = cargar_configuracion()
    return config.get(cliente_id, {
        'nombre_real': cliente_id,
        'versiones': 1,
        'expiracion': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
        'contacto': '',
        'activo': True
    })

# --------------------------
# 3️⃣ Funciones para procesamiento de datos
# --------------------------
def cargar_datos(rango_fechas=None):
    """Cargar todos los archivos CSV de la carpeta csv, opcionalmente filtrando por rango de fechas"""
    datos = []
    archivos = glob.glob(f'{CSV_FOLDER}/*.csv')
    
    # Si no hay archivos en la carpeta csv, buscar en la raíz (para compatibilidad)
    if not archivos:
        archivos = glob.glob('*.csv')
    
    for archivo in archivos:
        try:
            # Extraer fecha del nombre del archivo
            nombre_archivo = os.path.basename(archivo)
            fecha_match = re.search(r'(\d{4}-\d{2}-\d{2})', nombre_archivo)
            
            # Si el archivo tiene fecha en el nombre, verificar si está en el rango
            if fecha_match and rango_fechas:
                fecha_archivo = datetime.strptime(fecha_match.group(1), '%Y-%m-%d').date()
                fecha_inicio, fecha_fin = rango_fechas
                
                # Si el archivo está fuera del rango, saltarlo
                if fecha_archivo < fecha_inicio or fecha_archivo > fecha_fin:
                    continue
            
            df_temp = pd.read_csv(archivo)
            df_temp['Archivo'] = os.path.basename(archivo)
            
            # Intentar extraer fecha del nombre del archivo para usar como fecha de reporte
            if fecha_match:
                df_temp['Fecha_Reporte'] = fecha_match.group(1)
            else:
                # Si no hay fecha en el nombre, usar la fecha de modificación
                fecha_mod = datetime.fromtimestamp(os.path.getmtime(archivo))
                df_temp['Fecha_Reporte'] = fecha_mod.strftime('%Y-%m-%d')
            
            datos.append(df_temp)
        except Exception as e:
            print(f"Error cargando {archivo}: {e}")
    
    if datos:
        return pd.concat(datos, ignore_index=True)
    else:
        return pd.DataFrame()

def procesar_datos(df, rango_fechas=None):
    """Procesar los datos para el dashboard"""
    if df.empty:
        return (
            df, pd.Series(dtype=float), 0, 0, 
            pd.DataFrame(columns=['Mes', 'Total Clientes']), 
            pd.DataFrame(columns=['Mes', 'Clientes Nuevos']), 
            pd.DataFrame(columns=['Mes', 'Cliente', 'Ingresos']), 
            pd.DataFrame(columns=['Cliente', 'Reproducciones']), 
            pd.DataFrame(columns=['Cliente', 'Veces_pasadas']), 
            pd.DataFrame(columns=['Cliente', 'Reproducciones']), 
            pd.DataFrame(columns=['Dia_str', 'Reproducciones']),
            pd.DataFrame(columns=['Cliente', 'Versiones']),
            pd.DataFrame(columns=['Cliente', 'Total Segundos']),
            pd.DataFrame(columns=['Cliente', 'Nombre Real', 'Expiración', 'Días Restantes', 'Estado', 'Contacto'])
        )
    
    # Filtrar por rango de fechas si se especifica
    if rango_fechas:
        fecha_inicio, fecha_fin = rango_fechas
        # Convertir a datetime para comparación
        fecha_inicio = pd.to_datetime(fecha_inicio)
        fecha_fin = pd.to_datetime(fecha_fin) + timedelta(days=1)  # Incluir el día completo
        
        # Filtrar datos
        df = df[(pd.to_datetime(df['Playback Date']) >= fecha_inicio) & 
                (pd.to_datetime(df['Playback Date']) < fecha_fin)]
    
    # Convertir fechas a datetime
    df['Reported Date'] = pd.to_datetime(df['Reported Date'])
    df['Playback Date'] = pd.to_datetime(df['Playback Date'])
    
    # Extraer cliente del Media Name
    df['Cliente'] = df['Media Name'].str.extract(r'(cliente\d+)')[0]
    
    # CORRECCIÓN: Dividir la duración entre 1000 (6000 = 6 segundos)
    df['Media Duration Seconds'] = df['Media Duration'] / 1000
    
    # Extraer versión del Media Name
    df['Version'] = df['Media Name'].str.extract(r'(_v\d+)')[0].str.replace('_', '')
    df['Version'] = df['Version'].fillna('sin_version')
    
    # Calcular columnas para análisis
    df['Mes'] = df['Playback Date'].dt.to_period('M').astype(str)
    df['Dia_str'] = df['Playback Date'].dt.strftime('%Y-%m-%d')
    
    # Ocupación de espacio por pantalla (horas) - usando la duración corregida
    ocupacion = df.groupby('Monitor Name')['Media Duration Seconds'].sum() / 3600
    
    # Cantidad de clientes únicos
    clientes_unicos = df['Cliente'].nunique()
    
    # CALCULAR INGRESOS POR PROMEDIO (NUEVO)
    config = cargar_configuracion()
    clientes_activos = [k for k, v in config.items() if v.get('activo', True)]
    
    if clientes_activos:
        # Calcular promedio de clientes activos por mes
        df_activos = df[df['Cliente'].isin(clientes_activos)]
        clientes_mes = df_activos.groupby('Mes')['Cliente'].nunique().reset_index()
        
        # Calcular ingresos basado en el promedio mensual
        promedio_clientes_mes = clientes_mes['Cliente'].mean() if not clientes_mes.empty else 0
        ingresos_totales = promedio_clientes_mes * PRECIO_POR_CLIENTE * clientes_mes['Mes'].nunique()
        
        # Ingresos por mes para el gráfico
        clientes_mes['Ingresos'] = clientes_mes['Cliente'] * PRECIO_POR_CLIENTE
    else:
        ingresos_totales = 0
        clientes_mes = pd.DataFrame(columns=['Mes', 'Cliente', 'Ingresos'])
    
    # Clientes nuevos por mes (primer aparición)
    primer_aparicion = df.groupby('Cliente')['Playback Date'].min().dt.to_period('M').astype(str)
    clientes_nuevos_mes = primer_aparicion.value_counts().sort_index().reset_index()
    clientes_nuevos_mes.columns = ['Mes', 'Clientes Nuevos']
    
    # Clientes recurrentes por mes
    clientes_por_mes = df.groupby('Mes')['Cliente'].nunique().reset_index()
    clientes_por_mes.columns = ['Mes', 'Total Clientes']
    
    # Campañas programadas (cantidad de reproducciones por cliente)
    campanas = df.groupby('Cliente').size().reset_index(name='Reproducciones')
    
    # Frecuencia de paso de clientes
    frecuencia_clientes = df.groupby('Cliente')['Playback Date'].count().reset_index(name='Veces_pasadas')
    
    # Top clientes por reproducciones (todos, no solo 5)
    top_clientes_reproducciones = df.groupby('Cliente').size().reset_index(name='Reproducciones')
    top_clientes_reproducciones = top_clientes_reproducciones.sort_values('Reproducciones', ascending=False)
    
    # Evolución diaria de reproducciones
    evolucion_diaria = df.groupby('Dia_str').size().reset_index(name='Reproducciones')
    evolucion_diaria = evolucion_diaria.sort_values('Dia_str')
    
    # Versiones por cliente
    versiones_por_cliente = df.groupby('Cliente')['Version'].nunique().reset_index(name='Versiones')
    
    # Tiempo total por cliente (segundos REALES)
    tiempo_por_cliente = df.groupby('Cliente')['Media Duration Seconds'].sum().reset_index(name='Total Segundos')
    tiempo_por_cliente['Total Horas'] = tiempo_por_cliente['Total Segundos'] / 3600
    tiempo_por_cliente['Total Minutos'] = tiempo_por_cliente['Total Segundos'] / 60
    
    # Información de estado de clientes
    info_estado_clientes = []
    hoy = datetime.now().date()
    
    for cliente_id in df['Cliente'].unique():
        info = obtener_info_cliente(cliente_id)
        
        # Calcular días restantes
        try:
            fecha_exp = datetime.strptime(info['expiracion'], '%Y-%m-%d').date()
            dias_restantes = (fecha_exp - hoy).days
            estado = "✅ Activo" if dias_restantes > 7 else "⚠️ Por vencer" if dias_restantes > 0 else "❌ Vencido"
        except:
            dias_restantes = 0
            estado = "❌ Fecha inválida"
        
        info_estado_clientes.append({
            'Cliente': cliente_id,
            'Nombre Real': info['nombre_real'],
            'Expiración': info['expiracion'],
            'Días Restantes': dias_restantes,
            'Estado': estado,
            'Contacto': info['contacto'],
            'Versiones Config': info['versiones']
        })
    
    estado_clientes = pd.DataFrame(info_estado_clientes)
    
    return (
        df, ocupacion, clientes_unicos, ingresos_totales, 
        clientes_por_mes, clientes_nuevos_mes, clientes_mes, 
        campanas, frecuencia_clientes, top_clientes_reproducciones, 
        evolucion_diaria, versiones_por_cliente, tiempo_por_cliente,
        estado_clientes
    )

# --------------------------
# 4️⃣ Funciones para exportar testigos
# --------------------------
def buscar_videos_cliente(cliente_id):
    """Buscar videos de un cliente específico"""
    videos_folder = 'videos'  # Cambia por tu carpeta real de videos
    if os.path.exists(videos_folder):
        videos = []
        for root, dirs, files in os.walk(videos_folder):
            for file in files:
                if cliente_id in file and file.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.txt')):
                    videos.append(os.path.join(root, file))
        return videos
    return []

def extraer_testigo(video_path, output_folder, duracion=10):
    """Extraer un fragmento aleatorio de un video"""
    if not os.path.exists(video_path):
        return None
    
    # Para sistemas sin ffmpeg, creamos un archivo de prueba
    nombre_base = os.path.basename(video_path)
    nombre_testigo = f"testigo_{os.path.splitext(nombre_base)[0]}_{int(random.random()*1000)}.txt"
    output_path = os.path.join(output_folder, nombre_testigo)
    
    # Crear un archivo de prueba (en lugar de usar ffmpeg)
    with open(output_path, 'w') as f:
        f.write(f"Testigo extraído de: {nombre_base}\n")
        f.write(f"Cliente: {nombre_base}\n")
        f.write(f"Hora: {datetime.now()}\n")
        f.write(f"Duración: {duracion} segundos\n")
        f.write(f"Timestamp: {random.randint(0, 3600)}s\n")
    
    return output_path

def exportar_testigos_cliente(cliente_id, cantidad=3):
    """Exportar testigos de un cliente"""
    videos = buscar_videos_cliente(cliente_id)
    
    # Si no hay videos, crear algunos de ejemplo
    if not videos:
        ejemplo_path = f'videos/{cliente_id}_ejemplo.txt'
        os.makedirs('videos', exist_ok=True)
        with open(ejemplo_path, 'w') as f:
            f.write(f"Video de ejemplo para {cliente_id}\n")
        videos = [ejemplo_path]
    
    testigos_exportados = []
    for video in videos[:min(cantidad, len(videos))]:
        testigo_path = extraer_testigo(video, TESTIGOS_FOLDER)
        if testigo_path:
            testigos_exportados.append(testigo_path)
    
    return testigos_exportados

# --------------------------
# 5️⃣ Funciones para generar contratos PDF
# --------------------------
def generar_contrato_pdf(datos_contrato, output_path):
    """Generar un contrato en formato PDF basado en el documento proporcionado"""
    doc = SimpleDocTemplate(output_path, pagesize=letter,
                        rightMargin=72, leftMargin=72,
                        topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    elements = []
    
    # Encabezado
    elements.append(Paragraph("Grandes Redes S.A. de C.V.", styles['Title']))
    elements.append(Paragraph("Av. Salvador Nava Martinez #278, Col. El Paseo 78320 S.L.P.", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Datos del Cliente
    elements.append(Paragraph("Datos del Cliente", styles['Heading2']))
    
    # Tabla de datos del cliente
    cliente_data = [
        ['Nombre:', datos_contrato['nombre_cliente'], 'R.F.C.:', datos_contrato['rfc']],
        ['Domicilio:', datos_contrato['domicilio'], '', ''],
        ['Correo, Teléfono, Fax:', datos_contrato['contacto'], '', ''],
        ['Fecha:', datos_contrato['fecha_contrato'], 'N° de Orden:', datos_contrato['numero_orden']],
        ['Cliente Nuevo:', datos_contrato['cliente_nuevo'], 'Empresa:', datos_contrato['empresa']],
        ['Tiempo de Duración:', datos_contrato['duracion'], 'N° de Versiones:', datos_contrato['versiones']]
    ]
    
    cliente_table = Table(cliente_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 2*inch])
    cliente_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('SPAN', (1, 1), (3, 1)),
        ('SPAN', (1, 2), (3, 2)),
    ]))
    
    elements.append(cliente_table)
    elements.append(Spacer(1, 12))
    
    # Detalles de la Campaña
    elements.append(Paragraph("Detalles de la Campaña", styles['Heading2']))
    
    campana_data = [
        ['Diseño', 'Descripción del contenido', 'Duración y vigencia', 'Frecuencia de proyección', 'Horario / Programa', 'Formato Entregado', 'Precio Base', 'Descuento aplicado', 'IVA', 'Total'],
        [
            datos_contrato['diseno'], 
            datos_contrato['descripcion_contenido'], 
            datos_contrato['duracion_vigencia'], 
            datos_contrato['frecuencia_proyeccion'], 
            datos_contrato['horario_programa'], 
            datos_contrato['formato_entregado'], 
            datos_contrato['precio_base'], 
            datos_contrato['descuento'], 
            datos_contrato['iva'], 
            datos_contrato['total']
        ]
    ]
    
    campana_table = Table(campana_data, colWidths=[0.7*inch]*10)
    campana_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(campana_table)
    elements.append(Spacer(1, 12))
    
    # Información adicional
    elements.append(Paragraph("En caso de requerir diseño por parte de la empresa, mandar logotipo, corpus gráfico del producto o servicio que se ofrece, una imagen en formato JPG o PNG con calidad de 300 pixeles, slogan y breve presentación para proyectar la idea visual correctamente. El material deberá enviarse a: roberto.sanchez@gmnet.mx, martin.davila@gmnet.mx, ventas", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Condiciones Generales
    elements.append(Paragraph("Condiciones Generales", styles['Heading2']))
    condiciones = [
        "1. El Cliente entregará contenido en tiempo y forma según especificaciones técnicas.",
        "2. El Prestador garantizará proyección en condiciones óptimas.",
        "3. Todo material deberá respetar derechos de autor e imagen.",
        "4. El pago se realizará conforme a lo estipulado en la orden.",
        "5. Cancelaciones/modificaciones con mínimo 24 hrs de anticipación."
    ]
    
    for condicion in condiciones:
        elements.append(Paragraph(condicion, styles['Normal']))
    
    elements.append(Spacer(1, 12))
    
    # Firmas
    firmas_data = [
        ['_________________________', '_________________________', '_________________________'],
        ['Cliente', 'Gerencia de Ventas', 'Credito y Cobranza']
    ]
    
    firmas_table = Table(firmas_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
    elements.append(firmas_table)
    elements.append(Spacer(1, 12))
    
    # Texto adicional
    texto_adicional = "Por medio del presente pagaré, me comprometo incondicionalmente a liquidar la cantidad total de este contrato; sujeto a la cantidad de meses de transmisión requeridos y de acuerdo al importe del plan de publicidad seleccionado, cumpliendo el plazo de pago en los días de crédito marcados en este contrato. Las cancelaciones o modificaciones especiales, se aceptarán con un mínimo de 24 horas."
    elements.append(Paragraph(texto_adicional, styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Ficha Técnica
    elements.append(Paragraph("Ficha Tecnica.", styles['Heading2']))
    ficha_tecnica = "Resolución de 1320 x 840 pixeles, el formato de cointenido, video (reel) mp4, mov, en caso de imagen estatica: JPG o PNG, video con duración de 6 seg. hasta 20 versiones, área segura de diseño 1200x760 pixeles (para elemntos importantes). Texto legible a distancia, evitar frames neegros al inicio o final del video. codificación del video H.264/H.265. Peso maximo recomendado, video: 50 MB, imagen 10MB"
    elements.append(Paragraph(ficha_tecnica, styles['Normal']))
    
    # Construir el PDF
    doc.build(elements)
    return output_path

# Cargar datos iniciales
df, ocupacion, clientes_unicos, ingresos_totales, clientes_por_mes, clientes_nuevos_mes, ingresos_mes, campanas, frecuencia_clientes, top_clientes_reproducciones, evolucion_diaria, versiones_por_cliente, tiempo_por_cliente, estado_clientes = procesar_datos(cargar_datos())

# --------------------------
# 6️⃣ Layout del Dashboard
# --------------------------
app.layout = dbc.Container([
    # Título y carga de archivos
    dbc.Row([
        dbc.Col(html.H1("Dashboard Yodeck - Gestión de Clientes", className="text-center my-4"), width=12),
    ]),
    
    # Pestañas principales
    dbc.Tabs([
        # Pestaña 1: Dashboard principal
        dbc.Tab(label="Dashboard Principal", children=[
            dbc.Row([
                dbc.Col([
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([
                            'Arrastra o ',
                            html.A('selecciona un archivo CSV')
                        ]),
                        style={
                            'width': '100%',
                            'height': '60px',
                            'lineHeight': '60px',
                            'borderWidth': '1px',
                            'borderStyle': 'dashed',
                            'borderRadius': '5px',
                            'textAlign': 'center',
                            'margin': '10px'
                        },
                        multiple=True
                    ),
                    html.Div(id='output-data-upload'),
                ], width=12),
            ]),
            
            # Selector de rango de fechas
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Filtrar por Rango de Fechas"),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Fecha Inicio"),
                                    dcc.DatePickerSingle(
                                        id='fecha-inicio',
                                        display_format='YYYY-MM-DD',
                                        placeholder='Selecciona fecha inicio'
                                    ),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("Fecha Fin"),
                                    dcc.DatePickerSingle(
                                        id='fecha-fin',
                                        display_format='YYYY-MM-DD',
                                        placeholder='Selecciona fecha fin'
                                    ),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label(" "),
                                    dbc.Button("Aplicar Filtro", id='btn-filtrar-fechas', color='primary', className='mt-2'),
                                ], width=4),
                            ]),
                            html.Div(id='output-filtro-fechas', className='mt-2')
                        ])
                    ])
                ], width=12),
            ], className="mb-4"),
            
            # Tarjetas de métricas
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Clientes Activos", className="card-title"),
                            html.H2(f"{clientes_unicos}", className="card-text text-center", id="metric-clientes"),
                            html.P("Clientes con contenido", className="text-center")
                        ])
                    ], color="primary", inverse=True)
                ], width=3),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Ingresos Estimados", className="card-title"),
                            html.H2(f"${ingresos_totales:,.2f}", className="card-text text-center", id="metric-ingresos"),
                            html.P("Por promedio mensual", className="text-center")
                        ])
                    ], color="success", inverse=True)
                ], width=3),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Reproducciones", className="card-title"),
                            html.H2(f"{len(df)}", className="card-text text-center", id="metric-reproducciones"),
                            html.P("Total de spots", className="text-center")
                        ])
                    ], color="info", inverse=True)
                ], width=3),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Horas de Contenido", className="card-title"),
                            html.H2(f"{df['Media Duration Seconds'].sum()/3600:.1f}" if not df.empty else "0.0", 
                                    className="card-text text-center", id="metric-horas"),
                            html.P("Tiempo total real", className="text-center")
                        ])
                    ], color="warning", inverse=True)
                ], width=3),
            ], className="mb-4"),
            
            # Información de estado de clientes con botón de testigos
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Estado de Contratos de Clientes"),
                        dbc.CardBody([
                            html.Div(id='tabla-estado-clientes'),
                            html.Div(id='output-testigos', className='mt-3')
                        ])
                    ])
                ], width=12),
            ], className="mb-4"),
            
            # Gráficos principales
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Clientes por Mes"),
                        dbc.CardBody([
                            dcc.Graph(id='graph-clientes-mes')
                        ])
                    ])
                ], width=6),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Ingresos por Mes"),
                        dbc.CardBody([
                            dcc.Graph(id='graph-ingresos-mes')
                        ])
                    ])
                ], width=6),
            ], className="mb-4"),
            
            # Segunda fila de gráficos
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Reproducciones por Cliente"),
                        dbc.CardBody([
                            dcc.Graph(id='graph-top-clientes')
                        ])
                    ])
                ], width=6),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Tiempo por Cliente (minutos)"),
                        dbc.CardBody([
                            dcc.Graph(id='graph-tiempo-cliente')
                        ])
                    ])
                ], width=6),
            ], className="mb-4"),
            
            # Tercera fila de gráficos
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Evolución Diaria de Reproducciones"),
                        dbc.CardBody([
                            dcc.Graph(id='graph-evolucion-diaria')
                        ])
                    ])
                ], width=12),
            ], className="mb-4"),
        ]),
        
        # Pestaña 2: Gestión de Clientes
        dbc.Tab(label="Gestión de Clientes", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Agregar/Editar Cliente"),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("ID del Cliente (cliente1, cliente2, etc.)"),
                                    dbc.Input(id='input-cliente-id', type='text', placeholder='cliente1'),
                                ], width=6),
                                dbc.Col([
                                    dbc.Label("Nombre Real"),
                                    dbc.Input(id='input-nombre-real', type='text', placeholder='GlobalMedia'),
                                ], width=6),
                            ]),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Versiones"),
                                    dbc.Input(id='input-versiones', type='number', value=1, min=1),
                                ], width=3),
                                dbc.Col([
                                    dbc.Label("Fecha de Expiración"),
                                    dcc.DatePickerSingle(
                                        id='input-expiracion',
                                        date=datetime.now().date() + timedelta(days=30),
                                        display_format='YYYY-MM-DD'
                                    ),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("Contacto"),
                                    dbc.Input(id='input-contacto', type='text', placeholder='nombre@email.com'),
                                ], width=5),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Checklist(
                                        options=[{"label": "Cliente Activo", "value": 1}],
                                        value=[1],
                                        id='checklist-activo',
                                        switch=True,
                                    ),
                                ], width=12),
                            ], className='mt-3'),
                            dbc.Button("Guardar Cliente", id='btn-guardar-cliente', color='primary', className='mt-3'),
                            html.Div(id='output-guardar-cliente', className='mt-2')
                        ])
                    ])
                ], width=6),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Clientes Configurados"),
                        dbc.CardBody([
                            html.Div(id='tabla-clientes-config')
                        ])
                    ])
                ], width=6),
            ]),
        ]),
        
        # Pestaña 3: Creación de Contratos
        dbc.Tab(label="Creación de Contratos", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Datos del Contrato"),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Nombre del Cliente"),
                                    dbc.Input(id='contrato-nombre', type='text', placeholder='Nombre completo del cliente'),
                                ], width=6),
                                dbc.Col([
                                    dbc.Label("RFC"),
                                    dbc.Input(id='contrato-rfc', type='text', placeholder='RFC del cliente'),
                                ], width=6),
                            ]),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Domicilio"),
                                    dbc.Input(id='contrato-domicilio', type='text', placeholder='Domicilio completo'),
                                ], width=12),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Correo, Teléfono, Fax"),
                                    dbc.Input(id='contrato-contacto', type='text', placeholder='Información de contacto'),
                                ], width=12),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Fecha de Contrato"),
                                    dcc.DatePickerSingle(
                                        id='contrato-fecha',
                                        date=datetime.now().date(),
                                        display_format='YYYY-MM-DD'
                                    ),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("N° de Orden"),
                                    dbc.Input(id='contrato-numero-orden', type='text', placeholder='Número de orden'),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("Empresa"),
                                    dbc.Input(id='contrato-empresa', type='text', placeholder='Nombre de la empresa'),
                                ], width=4),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Cliente Nuevo"),
                                    dbc.Select(
                                        id='contrato-cliente-nuevo',
                                        options=[
                                            {'label': 'Sí', 'value': 'Sí'},
                                            {'label': 'No', 'value': 'No'}
                                        ],
                                        value='Sí'
                                    ),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("Tiempo de Duración"),
                                    dbc.Input(id='contrato-duracion', type='text', placeholder='Ej: 4 semanas'),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("N° de Versiones"),
                                    dbc.Input(id='contrato-versiones', type='number', value=1, min=1),
                                ], width=4),
                            ], className='mt-3'),
                        ])
                    ])
                ], width=6),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Detalles de la Campaña"),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Diseño"),
                                    dbc.Input(id='contrato-diseno', type='text', placeholder='Ej: Cliente / Prestador'),
                                ], width=6),
                                dbc.Col([
                                    dbc.Label("Descripción del contenido"),
                                    dbc.Input(id='contrato-descripcion', type='text', placeholder='Ej: Video 6 seg. / Imagen estática'),
                                ], width=6),
                            ]),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Duración y vigencia"),
                                    dbc.Input(id='contrato-vigencia', type='text', placeholder='Ej: 4 semanas, Inicio: 01/01/2023, Fin: 28/01/2023'),
                                ], width=12),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Frecuencia de proyección"),
                                    dbc.Input(id='contrato-frecuencia', type='text', placeholder='Ej: 10 veces/día (6 seg. c/u)'),
                                ], width=6),
                                dbc.Col([
                                    dbc.Label("Horario / Programa"),
                                    dbc.Input(id='contrato-horario', type='text', placeholder='Ej: 08:00 am -- 10:00 pm'),
                                ], width=6),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Formato Entregado"),
                                    dbc.Input(id='contrato-formato', type='text', placeholder='Ej: MP4 / JPG / PNG'),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("Precio Base ($)"),
                                    dbc.Input(id='contrato-precio', type='number', value=0, min=0),
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("Descuento aplicado (%)"),
                                    dbc.Input(id='contrato-descuento', type='number', value=0, min=0, max=100),
                                ], width=4),
                            ], className='mt-3'),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("IVA ($)"),
                                    dbc.Input(id='contrato-iva', type='number', value=0, min=0),
                                ], width=6),
                                dbc.Col([
                                    dbc.Label("Total ($)"),
                                    dbc.Input(id='contrato-total', type='number', value=0, min=0),
                                ], width=6),
                            ], className='mt-3'),
                            dbc.Button("Generar Contrato PDF", id='btn-generar-contrato', color='success', className='mt-3'),
                            html.Div(id='output-contrato', className='mt-2')
                        ])
                    ])
                ], width=6),
            ]),
        ]),
    ]),
    
    # Almacenamiento de datos
    dcc.Store(id='stored-data', data=df.to_dict('records')),
    dcc.Store(id='stored-config', data=cargar_configuracion()),
    dcc.Store(id='stored-fechas', data={'inicio': None, 'fin': None}),
    
], fluid=True)

# --------------------------
# 7️⃣ Callbacks para actualizar datos
# --------------------------
def parse_contents(contents, filename):
    """Parsear el contenido del archivo subido"""
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        if 'csv' in filename:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        else:
            return html.Div(['Solo se aceptan archivos CSV'])
    except Exception as e:
        print(e)
        return html.Div(['Hubo un error procesando el archivo'])
    
    # Guardar el archivo con fecha actual en la carpeta csv
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    nombre_archivo = f"{fecha_actual}_{filename}"
    ruta_archivo = os.path.join(CSV_FOLDER, nombre_archivo)
    
    df.to_csv(ruta_archivo, index=False)
    
    return html.Div([f'Archivo {filename} guardado como {nombre_archivo}!'])

def crear_tabla_estado_clientes(estado_clientes):
    """Crear tabla HTML con estado de clientes y botones de testigos"""
    if estado_clientes.empty:
        return html.Div("No hay datos de clientes disponibles")
    
    table_header = [
        html.Thead(html.Tr([
            html.Th("ID"), 
            html.Th("Nombre Real"), 
            html.Th("Versiones"), 
            html.Th("Expiración"),
            html.Th("Días Rest"),
            html.Th("Estado"),
            html.Th("Contacto"),
            html.Th("Testigos")
        ]))
    ]
    
    rows = []
    for _, row in estado_clientes.iterrows():
        # Color según estado
        color = "success" if "✅" in row['Estado'] else "warning" if "⚠️" in row['Estado'] else "danger"
        
        rows.append(html.Tr([
            html.Td(row['Cliente']),
            html.Td(row['Nombre Real']),
            html.Td(row['Versiones Config']),
            html.Td(row['Expiración']),
            html.Td(row['Días Restantes'], style={'color': 'red' if row['Días Restantes'] < 0 else 'orange' if row['Días Restantes'] < 7 else 'green'}),
            html.Td(dbc.Badge(row['Estado'], color=color)),
            html.Td(row['Contacto']),
            html.Td(
                dbc.Button(
                    "🎬 Exportar Testigos", 
                    id={'type': 'btn-testigos', 'index': row['Cliente']},
                    size='sm', 
                    color='info',
                    className='me-1'
                )
            )
        ]))
    
    table_body = [html.Tbody(rows)]
    return dbc.Table(table_header + table_body, bordered=True, hover=True, responsive=True, striped=True)

def crear_tabla_clientes_config():
    """Crear tabla de clientes configurados"""
    config = cargar_configuracion()
    
    if not config:
        return html.Div("No hay clientes configurados")
    
    table_header = [
        html.Thead(html.Tr([
            html.Th("ID"), 
            html.Th("Nombre Real"), 
            html.Th("Versiones"), 
            html.Th("Expiración"),
            html.Th("Estado"),
            html.Th("Acciones")
        ]))
    ]
    
    rows = []
    for cliente_id, info in config.items():
        estado = "✅ Activo" if info.get('activo', True) else "❌ Inactivo"
        color = "success" if info.get('activo', True) else "danger"
        
        rows.append(html.Tr([
            html.Td(cliente_id),
            html.Td(info.get('nombre_real', cliente_id)),
            html.Td(info.get('versiones', 1)),
            html.Td(info.get('expiracion', '')),
            html.Td(dbc.Badge(estado, color=color)),
            html.Td(
                dbc.Button("✏️", id=f'btn-editar-{cliente_id}', size='sm', color='warning', className='me-1') +
                dbc.Button("🗑️", id=f'btn-eliminar-{cliente_id}', size='sm', color='danger')
            )
        ]))
    
    table_body = [html.Tbody(rows)]
    return dbc.Table(table_header + table_body, bordered=True, hover=True, responsive=True)

@app.callback(
    [Output('stored-data', 'data'),
     Output('output-data-upload', 'children'),
     Output('metric-clientes', 'children'),
     Output('metric-ingresos', 'children'),
     Output('metric-reproducciones', 'children'),
     Output('metric-horas', 'children'),
     Output('tabla-estado-clientes', 'children'),
     Output('graph-clientes-mes', 'figure'),
     Output('graph-ingresos-mes', 'figure'),
     Output('graph-top-clientes', 'figure'),
     Output('graph-tiempo-cliente', 'figure'),
     Output('graph-evolucion-diaria', 'figure'),
     Output('output-filtro-fechas', 'children')],
    [Input('upload-data', 'contents'),
     Input('btn-filtrar-fechas', 'n_clicks'),
     Input('stored-config', 'data')],
    [State('upload-data', 'filename'),
     State('stored-data', 'data'),
     State('fecha-inicio', 'date'),
     State('fecha-fin', 'date'),
     State('stored-fechas', 'data')],
    prevent_initial_call=False
)
def update_data(contents, n_clicks_filtro, config_data, filenames, stored_data, fecha_inicio, fecha_fin, fechas_actuales):
    """Actualizar los datos cuando se sube un nuevo archivo, cambia la configuración o se aplica filtro de fechas"""
    
    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    # Si se subió un nuevo archivo
    if contents is not None and trigger_id == 'upload-data':
        for content, filename in zip(contents, filenames):
            resultado_upload = parse_contents(content, filename)
    
    # Determinar rango de fechas a usar
    rango_fechas = None
    mensaje_filtro = ""
    
    # Si se hizo clic en el botón de filtrar
    if trigger_id == 'btn-filtrar-fechas' and fecha_inicio and fecha_fin:
        rango_fechas = (pd.to_datetime(fecha_inicio).date(), pd.to_datetime(fecha_fin).date())
        mensaje_filtro = f"Filtro aplicado: {fecha_inicio} a {fecha_fin}"
    # Si hay fechas almacenadas
    elif fechas_actuales and fechas_actuales['inicio'] and fechas_actuales['fin']:
        rango_fechas = (pd.to_datetime(fechas_actuales['inicio']).date(), 
                        pd.to_datetime(fechas_actuales['fin']).date())
        mensaje_filtro = f"Filtro aplicado: {fechas_actuales['inicio']} a {fechas_actuales['fin']}"
    
    # Recargar y procesar datos
    df = cargar_datos(rango_fechas)
    (df_processed, ocupacion, clientes_unicos, ingresos_totales, 
     clientes_por_mes, clientes_nuevos_mes, ingresos_mes, 
     campanas, frecuencia_clientes, top_clientes_reproducciones, 
     evolucion_diaria, versiones_por_cliente, tiempo_por_cliente,
     estado_clientes) = procesar_datos(df, rango_fechas)
    
    # Actualizar métricas
    metric_clientes = f"{clientes_unicos}"
    metric_ingresos = f"${ingresos_totales:,.2f}"
    metric_reproducciones = f"{len(df_processed)}"
    metric_horas = f"{df_processed['Media Duration Seconds'].sum()/3600:.1f}" if not df_processed.empty else "0.0"
    
    # Crear tabla de estado de clientes
    tabla_estado = crear_tabla_estado_clientes(estado_clientes)
    
    # Actualizar gráficos
    fig_clientes_mes = px.bar(clientes_por_mes, x='Mes', y='Total Clientes', 
                             title="Clientes Activos por Mes") if not clientes_por_mes.empty else go.Figure()
    
    if not clientes_por_mes.empty:
        ingresos_mes_data = clientes_por_mes.copy()
        ingresos_mes_data['Ingresos'] = ingresos_mes_data['Total Clientes'] * PRECIO_POR_CLIENTE
        fig_ingresos_mes = px.line(ingresos_mes_data, x='Mes', y='Ingresos', markers=True,
                                  title="Ingresos Mensuales Estimados")
        fig_ingresos_mes.update_traces(line=dict(color='green', width=3))
    else:
        fig_ingresos_mes = go.Figure()
    
    # Aplicar nombres reales a los gráficos
    nombres_reales = obtener_nombres_reales()
    if not top_clientes_reproducciones.empty:
        top_clientes_reproducciones['Nombre Real'] = top_clientes_reproducciones['Cliente'].map(
            lambda x: nombres_reales.get(x, x)
        )
        fig_top_clientes = px.bar(top_clientes_reproducciones, x='Nombre Real', y='Reproducciones',
                                 title="Reproducciones por Cliente")
    else:
        fig_top_clientes = go.Figure()
    
    if not tiempo_por_cliente.empty:
        tiempo_por_cliente['Nombre Real'] = tiempo_por_cliente['Cliente'].map(
            lambda x: nombres_reales.get(x, x)
        )
        fig_tiempo_cliente = px.bar(tiempo_por_cliente, x='Nombre Real', y='Total Minutos',
                                   title="Minutos de Contenido por Cliente")
    else:
        fig_tiempo_cliente = go.Figure()
    
    # Gráfico de evolución diaria
    if not evolucion_diaria.empty:
        fig_evolucion_diaria = px.line(evolucion_diaria, x='Dia_str', y='Reproducciones', markers=True,
                                      title="Reproducciones por Día")
    else:
        fig_evolucion_diaria = go.Figure()
        fig_evolucion_diaria.update_layout(title="Reproducciones por Día")
    
    # Mensaje de upload si corresponde
    mensaje_upload = html.Div([f"Datos actualizados. {len(df_processed)} registros de {clientes_unicos} clientes."])
    if contents is not None and trigger_id == 'upload-data':
        mensaje_upload = resultado_upload
    
    return (
        df_processed.to_dict('records'), 
        mensaje_upload,
        metric_clientes, metric_ingresos, metric_reproducciones, metric_horas,
        tabla_estado,
        fig_clientes_mes, fig_ingresos_mes, fig_top_clientes, 
        fig_tiempo_cliente, fig_evolucion_diaria,
        html.Div(mensaje_filtro, style={'color': 'green'}) if mensaje_filtro else html.Div("Sin filtro de fechas")
    )

@app.callback(
    Output('stored-fechas', 'data'),
    [Input('btn-filtrar-fechas', 'n_clicks')],
    [State('fecha-inicio', 'date'),
     State('fecha-fin', 'date')]
)
def actualizar_fechas_almacenadas(n_clicks, fecha_inicio, fecha_fin):
    """Almacenar las fechas de filtro seleccionadas"""
    if n_clicks:
        return {'inicio': fecha_inicio, 'fin': fecha_fin}
    return no_update

@app.callback(
    [Output('output-guardar-cliente', 'children'),
     Output('stored-config', 'data'),
     Output('tabla-clientes-config', 'children')],
    [Input('btn-guardar-cliente', 'n_clicks')],
    [State('input-cliente-id', 'value'),
     State('input-nombre-real', 'value'),
     State('input-versiones', 'value'),
     State('input-expiracion', 'date'),
     State('input-contacto', 'value'),
     State('checklist-activo', 'value'),
     State('stored-config', 'data')]
)
def guardar_cliente(n_clicks, cliente_id, nombre_real, versiones, expiracion, contacto, activo, config_data):
    """Guardar la configuración de un cliente"""
    if n_clicks is None or not cliente_id:
        return no_update, no_update, no_update
    
    if not cliente_id.startswith('cliente'):
        return html.Div("❌ El ID debe empezar con 'cliente' (ej: cliente1)", style={'color': 'red'}), no_update, no_update
    
    # Cargar configuración actual
    config = cargar_configuracion()
    
    # Actualizar configuración
    config[cliente_id] = {
        'nombre_real': nombre_real or cliente_id,
        'versiones': versiones or 1,
        'expiracion': expiracion or (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
        'contacto': contacto or '',
        'activo': bool(activo)
    }
    
    # Guardar configuración
    guardar_configuracion(config)
    
    # Actualizar tabla
    tabla = crear_tabla_clientes_config()
    
    return html.Div("✅ Cliente guardado correctamente", style={'color': 'green'}), config, tabla

@app.callback(
    Output('tabla-clientes-config', 'children', allow_duplicate=True),
    [Input('stored-config', 'data')],
    prevent_initial_call=True
)
def actualizar_tabla_clientes(config_data):
    """Actualizar tabla de clientes cuando cambia la configuración"""
    return crear_tabla_clientes_config()

@app.callback(
    Output('output-testigos', 'children'),
    [Input({'type': 'btn-testigos', 'index': ALL}, 'n_clicks')],
    [State({'type': 'btn-testigos', 'index': ALL}, 'id')],
    prevent_initial_call=True
)
def exportar_testigos(n_clicks, ids):
    """Exportar testigos cuando se hace clic en el botón"""
    if not callback_context.triggered:
        return no_update
    
    # Obtener el ID del cliente que disparó el callback
    button_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    if not button_id or button_id == '':
        return no_update
    
    try:
        cliente_id = json.loads(button_id.replace("'", "\""))['index']
    except:
        return html.Div("❌ Error al procesar la solicitud", style={'color': 'red'})
    
    # Exportar testigos
    testigos = exportar_testigos_cliente(cliente_id)
    
    if testigos:
        return html.Div([
            html.H5(f"Testigos exportados para {cliente_id}:"),
            html.Ul([html.Li(os.path.basename(t)) for t in testigos]),
            html.P("Los testigos se guardaron en la carpeta 'testigos'", style={'color': 'green'})
        ])
    else:
        return html.Div([
            html.P("❌ No se encontraron videos para este cliente", style={'color': 'red'}),
            html.P("Asegúrate de tener los videos en la carpeta 'videos'")
        ])

@app.callback(
    [Output('output-contrato', 'children'),
     Output('contrato-total', 'value')],
    [Input('btn-generar-contrato', 'n_clicks'),
     Input('contrato-precio', 'value'),
     Input('contrato-descuento', 'value'),
     Input('contrato-iva', 'value')],
    [State('contrato-nombre', 'value'),
     State('contrato-rfc', 'value'),
     State('contrato-domicilio', 'value'),
     State('contrato-contacto', 'value'),
     State('contrato-fecha', 'date'),
     State('contrato-numero-orden', 'value'),
     State('contrato-empresa', 'value'),
     State('contrato-cliente-nuevo', 'value'),
     State('contrato-duracion', 'value'),
     State('contrato-versiones', 'value'),
     State('contrato-diseno', 'value'),
     State('contrato-descripcion', 'value'),
     State('contrato-vigencia', 'value'),
     State('contrato-frecuencia', 'value'),
     State('contrato-horario', 'value'),
     State('contrato-formato', 'value')]
)
def generar_contrato(n_clicks, precio, descuento, iva, nombre, rfc, domicilio, contacto, fecha, 
                    numero_orden, empresa, cliente_nuevo, duracion, versiones, diseno, descripcion, 
                    vigencia, frecuencia, horario, formato):
    """Generar contrato PDF cuando se hace clic en el botón"""
    if n_clicks is None:
        return no_update, no_update
    
    # Calcular total automáticamente si no se ha especificado
    if precio is not None and descuento is not None and iva is not None:
        descuento_valor = precio * (descuento / 100)
        total = precio - descuento_valor + iva
    else:
        total = 0
    
    # Si se está calculando automáticamente, solo actualizar el total
    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if trigger_id != 'btn-generar-contrato':
        return no_update, total
    
    # Validar campos obligatorios
    if not all([nombre, rfc, domicilio, contacto, fecha, numero_orden]):
        return html.Div("❌ Por favor complete todos los campos obligatorios", style={'color': 'red'}), total
    
    # Preparar datos para el contrato
    datos_contrato = {
        'nombre_cliente': nombre or '',
        'rfc': rfc or '',
        'domicilio': domicilio or '',
        'contacto': contacto or '',
        'fecha_contrato': fecha or datetime.now().strftime('%Y-%m-%d'),
        'numero_orden': numero_orden or '',
        'empresa': empresa or '',
        'cliente_nuevo': cliente_nuevo or 'Sí',
        'duracion': duracion or '',
        'versiones': str(versiones or '1'),
        'diseno': diseno or '',
        'descripcion_contenido': descripcion or '',
        'duracion_vigencia': vigencia or '',
        'frecuencia_proyeccion': frecuencia or '',
        'horario_programa': horario or '',
        'formato_entregado': formato or '',
        'precio_base': f"${precio or 0:,.2f}",
        'descuento': f"{descuento or 0}%",
        'iva': f"${iva or 0:,.2f}",
        'total': f"${total:,.2f}"
    }
    
    # Generar nombre del archivo
    nombre_archivo = f"contrato_{nombre.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ruta_archivo = os.path.join(CONTRATOS_FOLDER, nombre_archivo)
    
    try:
        # Generar el PDF
        generar_contrato_pdf(datos_contrato, ruta_archivo)
        
        return html.Div([
            html.P("✅ Contrato generado correctamente", style={'color': 'green'}),
            html.P(f"Archivo: {nombre_archivo}"),
            html.A("Descargar contrato", href=f"/assets/contratos/{nombre_archivo}", target="_blank")
        ]), total
    except Exception as e:
        return html.Div(f"❌ Error al generar el contrato: {str(e)}", style={'color': 'red'}), total

# --------------------------
# 8️⃣ Ejecutar servidor
# --------------------------
if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    os.makedirs('testigos', exist_ok=True)
    os.makedirs('videos', exist_ok=True)
    os.makedirs('csv', exist_ok=True)
    os.makedirs('contratos', exist_ok=True)
    
    # Crear carpeta assets para servir archivos estáticos
    os.makedirs('assets/contratos', exist_ok=True)
    
    app.run(debug=True)