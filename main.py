import email
from dotenv import load_dotenv
import os
import imaplib
import re
from licitacion import Licitacion
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

#Configuración
dias= 3                                                #dias que puede ir atrás en correo para buscar licitaciones
asunto= "Correu diari de subscriptors generals"         #Asunto que quieres buscar en los correos
colorEmpleador="#660303"                                #Color en el cual esta escrito el empleador en el correo

# Cargar variables de entorno (.env)
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# Cambia este si usas otro proveedor de correo
IMAP_SERVER = "imap.gmail.com"

from dataclasses import dataclass


def connect_to_email():
    print("Conectando al correo...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("inbox")
    return mail

def buscar_correo_por_asunto(mail, asunto_buscado):
    # Obtener todos los IDs de correo hasta la fecha límite
    fecha_limite = (datetime.now() - timedelta(days=dias)).strftime('%d-%b-%Y')
    status, data = mail.search(None, 'SINCE', fecha_limite)
    if status != "OK":
        print("❌ No se pudieron recuperar los correos.")
        return None

    email_ids = data[0].split()
    email_ids.reverse()  # Buscar desde el más reciente

    for eid in email_ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue

        raw_email = msg_data[0][1]
        message = email.message_from_bytes(raw_email)
        subject = message["Subject"]
        print("Mensaje a analizar: "+subject)

        if subject and asunto.lower() in subject.lower():
            print("\n✅ Correo encontrado:")
            print("Asunto:", subject)
            fecha_raw = message["Date"]
            fecha_formateada = parsedate_to_datetime(fecha_raw).strftime('%d/%m/%Y')    #formatear la fecha
            print("Fecha:", fecha_formateada)
            return message  # Devuelve el mensaje completo

    print("⚠️ No se encontró ningún correo con ese asunto.")
    return None

def eliminar_encabezado_reenviado(texto):
    lineas = texto.splitlines()
    resultado = []
    saltando = False
    for linea in lineas:
        if any(linea.strip().lower().startswith(prefix) for prefix in ["de:", "enviado el:", "para:", "asunto:"]):
            saltando = True
            continue
        if saltando and linea.strip() == "":
            saltando = False
            continue
        if not saltando:
            resultado.append(linea)
    return "\n".join(resultado)

def extraer_html_del_mensaje(mensaje):
    if mensaje.is_multipart():
        for part in mensaje.walk():
            if part.get_content_type() == "text/html":
                html = part.get_payload(decode=True).decode(errors="ignore")
                return html
    return None

def extraer_licitaciones_desde_html(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    licitaciones = []
    empleador_actual = None

    for tag in soup.find_all():
        # 🟥 Detectar empleador por color rojo exacto
        if tag.name in ["b", "strong"] and tag.find("span", style=lambda s: s and colorEmpleador in s.lower()):
            empleador_actual = tag.get_text(strip=True)

        # 🔗 Detectar enlaces de licitación válidos únicamente
        elif tag.name == "a" and "href" in tag.attrs:
            enlace = tag["href"]

            # ✅ Solo procesar enlaces válidos de licitaciones
            if not enlace.startswith("https://contractaciopublica.cat/ca/detall-publicacio/estado/"):
                continue  # Saltar enlaces tipo "feu clic aquí"

            titulo = tag.get_text(strip=True)

            # Obtener los siguientes <p> con info adicional
            siguiente_info = tag.find_parent("p").find_next_siblings("p", limit=3)
            fecha_publicacion, fecha_limite, presupuesto = "", "", ""

            for p in siguiente_info:
                texto = p.get_text(strip=True).lower()
                if "data de publicació" in texto:
                    fecha_publicacion = texto.split(":", 1)[1].strip()
                elif "termini de presentació" in texto:
                    fecha_limite = texto.split(":", 1)[1].strip()
                elif "pressupost de licitació" in texto:
                    presupuesto = texto.split(":", 1)[1].strip()

            lic = Licitacion(
                empleador=empleador_actual or "",
                titulo=titulo,
                enlace=enlace,
                fecha_publicacion=fecha_publicacion,
                fecha_limite=fecha_limite,
                presupuesto=presupuesto
            )

            licitaciones.append(lic)

    return licitaciones

def parsear_licitaciones(texto):
    # Dividir el texto en bloques de licitaciones (separados por 2+ saltos de línea)
    bloques = re.split(r'\n', texto.strip())

    licitaciones = []

    for bloque in bloques:
        if not bloque.strip():
            continue

        try:
            # Extraer título (todo hasta el enlace)
            #empleador=

            titulo_match = re.search(r'^(.*?)\s*<https?://', bloque, re.DOTALL)
            titulo = titulo_match.group(1).strip() if titulo_match else "Sin título"

            # Extraer enlace
            enlace_match = re.search(r'<(https?://[^\s>]+)>', bloque)
            enlace = enlace_match.group(1) if enlace_match else "Sin enlace"

            # Extraer fechas y presupuesto
            fecha_pub_match = re.search(r'Data de publicació:\s*(.*?)\s*h', bloque)
            fecha_pub = fecha_pub_match.group(1) if fecha_pub_match else "Fecha desconocida"

            fecha_lim_match = re.search(r'Termini de presentació d\'ofertes:\s*(.*?)\s*h', bloque)
            fecha_lim = fecha_lim_match.group(1) if fecha_lim_match else "Fecha límite desconocida"

            presupuesto_match = re.search(r'Pressupost de licitació:\s*([\d.,]+)\s*€', bloque)
            presupuesto = f"{presupuesto_match.group(1)} € sense IVA" if presupuesto_match else "Presupuesto no especificado"

            # Crear objeto Licitacion
            licitacion = Licitacion(
                titulo=titulo,
                enlace=enlace,
                fecha_publicacion=fecha_pub,
                fecha_limite=fecha_lim,
                presupuesto=presupuesto
            )

            licitaciones.append(licitacion)

        except Exception as e:
            print(
                f"Error procesando bloque: {e}\n{bloque[:200]}...")  # Mostrar solo el inicio del bloque para no saturar la salida

    return licitaciones


def filtrado_inicial(licitaciones: list) -> list:

    #TODO Meter los primeros filtros, como la fecha o el importe insuficientes

    return licitaciones


def main():
    #Encontrar el correo
    mail = connect_to_email()
    mensaje = buscar_correo_por_asunto(mail, asunto)
    mail.logout()
    if not mensaje:
        print("❌ No se encontró ningún correo reciente con ese asunto.")
        return

    html = extraer_html_del_mensaje(mensaje)
    if html:
        licitaciones = extraer_licitaciones_desde_html(html)
        print(f"\n📋 Se detectaron {len(licitaciones)} licitaciones desde HTML:")

    licitaciones_filtradas = filtrado_inicial(licitaciones)
    print(f"\n📋 Se detectaron {len(licitaciones_filtradas)} licitaciones desde HTML:")
    for i, lic in enumerate(licitaciones_filtradas, 1):
        print(f"\n🔹 Licitación {i}:")
        print(lic.to_print())

if __name__ == "__main__":
    main()