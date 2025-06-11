import email
from dotenv import load_dotenv
import os
import imaplib
import re
from licitacion import Licitacion
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import shutil
import time

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

def descargar_pdfs_licitacion(licitacion: Licitacion, carpeta_destino: str = "pdfs"):
    url = licitacion.GetEnlace()
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Error al acceder a {url}: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Crear carpeta si no existe
    os.makedirs(carpeta_destino, exist_ok=True)

    pdf_links = soup.find_all("a", href=True)
    encontrados = 0

    for link in pdf_links:
        texto = link.get_text(strip=True).lower()
        href = link["href"]

        # Filtro por nombre asociado a los PDF deseados
        if "administratives" in texto or "prescripcions tècniques" in texto:
            nombre_pdf = texto.replace(" ", "_").replace("/", "_") + ".pdf"

            if not href.startswith("http"):
                href = "https://contractaciopublica.cat" + href  # enlace relativo

            ruta_pdf = os.path.join(carpeta_destino, nombre_pdf)

            try:
                pdf_data = requests.get(href, headers=headers)
                with open(ruta_pdf, "wb") as f:
                    f.write(pdf_data.content)
                print(f"✅ PDF descargado: {nombre_pdf}")
                encontrados += 1
            except Exception as e:
                print(f"❌ Error al descargar {href}: {e}")

    if encontrados == 0:
        print("⚠️ No se encontraron PDFs relevantes en esta licitación.")


def descargar_pdfs_con_selenium(licitacion: Licitacion, carpeta_destino: str = "pdfs"):
    enlace = licitacion.GetEnlace()

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # para que no abra ventana
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(enlace)

    # Esperar que cargue el contenido JS
    time.sleep(3)

    os.makedirs(carpeta_destino, exist_ok=True)
    encontrados = 0

    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            texto = link.text.lower()
            if "administratives" in texto or "prescripcions tècniques" in texto:
                href = link.get_attribute("href")
                if href and href.endswith(".pdf"):
                    nombre = texto.replace(" ", "_").replace("/", "_") + ".pdf"
                    ruta = os.path.join(carpeta_destino, nombre)
                    try:
                        r = requests.get(href)
                        with open(ruta, "wb") as f:
                            f.write(r.content)
                        print(f"✅ PDF descargado: {nombre}")
                        encontrados += 1
                    except Exception as e:
                        print(f"❌ Error al descargar {href}: {e}")
    finally:
        driver.quit()

    if encontrados == 0:
        print("⚠️ No se encontraron PDFs en esta licitación.")


def descargar_pdfs_clickando_selectivamente(licitacion, carpeta_destino="pdfs", carpeta_temp="tmp_descargas"):
    url = licitacion.GetEnlace()
    nombre_base = licitacion.GetTitulo().replace(" ", "_").replace("/", "_")

    os.makedirs(carpeta_destino, exist_ok=True)
    os.makedirs(carpeta_temp, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(carpeta_temp),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    })

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    time.sleep(3)

    claves_buscadas = [
        "plec de clàusules administratives",
        "plec de prescripcions tècniques"
    ]

    encontrados = 0
    try:
        rows = driver.find_elements(By.CLASS_NAME, "row")

        for row in rows:
            label_div = row.find_element(By.CLASS_NAME, "col-md-4")
            label_text = label_div.text.strip().lower()

            if any(clave in label_text for clave in claves_buscadas):
                try:
                    button_div = row.find_element(By.CLASS_NAME, "col-md-8")
                    enlaces = button_div.find_elements(By.TAG_NAME, "a")
                    if not enlaces:
                        print(f"⚠️ No se encontró enlace PDF en: {label_text}")
                        continue
                    enlace = enlaces[0]
                    href = enlace.get_attribute("href")
                    encontrados += 1
                    time.sleep(2)  # espera a que descargue
                except Exception as e:
                    print(f"❌ No se pudo hacer clic en el botón de: {label_text} → {e}")

        time.sleep(4)  # espera adicional
    finally:
        driver.quit()

    # Mover PDFs a carpeta final
    for filename in os.listdir(carpeta_temp):
        if filename.lower().endswith(".pdf"):
            destino = os.path.join(carpeta_destino, f"{nombre_base}__{filename}")
            origen = os.path.join(carpeta_temp, filename)
            shutil.move(origen, destino)
            print(f"✅ Guardado: {destino}")

    if encontrados == 0:
        print("⚠️ No se encontraron documentos administrativos o técnicos.")

    shutil.rmtree(carpeta_temp, ignore_errors=True)

def descargar_pdfs_por_href(licitacion, carpeta_destino="pdfs"):
    url = licitacion.GetEnlace()
    nombre_base = licitacion.GetTitulo().replace(" ", "_").replace("/", "_")

    os.makedirs(carpeta_destino, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    time.sleep(3)  # permitir que cargue el DOM

    claves_buscadas = [
        "plec de clàusules administratives",
        "plec de prescripcions tècniques"
    ]

    contador = 1        #Eliminar mas tarde cuando se decida como guardar los pdfs

    encontrados = 0

    try:
        rows = driver.find_elements(By.CLASS_NAME, "row")

        for row in rows:
            try:
                label_div = row.find_element(By.CLASS_NAME, "col-md-4")
                label_text = label_div.text.strip().lower()

                if any(clave in label_text for clave in claves_buscadas):
                    link_div = row.find_element(By.CLASS_NAME, "col-md-8")
                    enlaces = link_div.find_elements(By.TAG_NAME, "a")

                    if not enlaces:
                        print(f"⚠️ No se encontró enlace PDF en: {label_text}")
                        continue

                    enlace = enlaces[0]
                    href = enlace.get_attribute("href")
                    texto_link = enlace.text.strip()

                    if href:
                        nombre = f"{contador}.pdf"
                        destino = os.path.join(carpeta_destino, nombre)

                        try:
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                            }
                            r = requests.get(href, headers=headers)
                            with open(destino, "wb") as f:
                                f.write(r.content)
                            print(f"✅ PDF guardado como {nombre}")
                            contador += 1
                            encontrados += 1
                        except Exception as e:
                            print(f"❌ Error al descargar desde {href}: {e}")
            except Exception:
                continue

    finally:
        driver.quit()

    if encontrados == 0:
        print("⚠️ No se encontró ningún documento técnico o administrativo.")



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

    print(licitaciones[0].to_print())
    #descargar_pdfs_con_selenium(licitaciones[0])
    #descargar_pdfs_clickando_selectivamente(licitaciones[0])
    descargar_pdfs_por_href(licitaciones[0])


if __name__ == "__main__":
    main()