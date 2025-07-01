import csv
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
from pdf_analisis import openAIRequest, cargar_prompts_desde_txt, filtrar_por_tematicas

#Configuración
dias= 30                                                #dias que puede ir atrás en correo para buscar licitaciones
asunto= "Correu diari de subscriptors generals"         #Asunto que quieres buscar en los correos
presupuestoLimite=500000                                #Precio minimo por el cual aceptamos las licitaciones
diasLimite=3 #26                                       #Plazo para hacer la licitación mínimo
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
                presupuesto=presupuesto,
                administratives="",
                tecniques=""
            )

            licitaciones.append(lic)

    return licitaciones

def filtrado_inicial(licitaciones: list) -> list:
    resultado = []
    hoy = datetime.today()

    for lic in licitaciones:
        # Validar fecha límite
        fecha_limite_str = lic.GetFecha_limite().strip().split(" ")[0]  # Solo la parte de la fecha
        fecha_limite_str = fecha_limite_str.replace("h", "").strip()  # Por si acaso
        try:
            fecha_limite = datetime.strptime(fecha_limite_str, "%d/%m/%Y")
            dias_restantes = (fecha_limite - hoy).days
            if dias_restantes < diasLimite:
                print(f" ❌ DESCARTADA por fecha: {lic.GetTitulo()} (quedan {dias_restantes} días)")
                continue
        except Exception:
            print(f"⚠️ DESCARTADA por fecha inválida: {lic.GetTitulo()} ({fecha_limite_str})")
            continue
        # Validar presupuesto
        presupuesto_str = lic.GetPresupuesto().lower()
        presupuesto_str = presupuesto_str.replace("sense iva", "")
        presupuesto_str = presupuesto_str.replace("€", "")
        presupuesto_str = presupuesto_str.replace(".", "")
        presupuesto_str = presupuesto_str.replace(",", ".")
        presupuesto_str = presupuesto_str.strip()
        try:
            presupuesto = float(presupuesto_str)
            if presupuesto < presupuestoLimite:
                print(f" ❌ DESCARTADA por presupuesto: {lic.GetTitulo()} ({presupuesto:.2f} €)")
                continue
        except Exception:
            print(f"⚠️ DESCARTADA por presupuesto inválido: {lic.GetTitulo()} ({lic.GetPresupuesto()})")
            continue

        resultado.append(lic)
    return resultado

def limpiar_nombre(texto):
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\s-]", "", texto)
    texto = texto.replace(" ", "_")
    return texto[:80]

def descargar_pdfs_por_href(licitacion, carpeta_base="pdfs"):
    url = licitacion.GetEnlace()
    titulo = licitacion.GetTitulo()
    carpeta_licitacion = os.path.join(carpeta_base, limpiar_nombre(titulo))
    os.makedirs(carpeta_licitacion, exist_ok=True)


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
                        print(f"⚠️ No se encontró enlace en: {label_text}")
                        continue

                    enlace = enlaces[0]
                    href = enlace.get_attribute("href")

                    if href:
                        # Determinar el nombre del archivo según la clave detectada
                        if "administratives" in label_text:
                            nombre_archivo = "administratives.pdf"
                        elif "tècniques" in label_text:
                            nombre_archivo = "tecniques.pdf"
                        else:
                            continue  # No coincide con las claves conocidas

                        destino = os.path.join(carpeta_licitacion, nombre_archivo)

                        if "administratives" in label_text:
                            licitacion.SetAdministratives(destino)
                        elif "tècniques" in label_text:
                            licitacion.SetTecniques(destino)

                        if os.path.exists(destino):
                            print(f" ❌ Ya existia: {destino}")
                            continue
                        try:
                            headers = {"User-Agent": "Mozilla/5.0"}
                            r = requests.get(href, headers=headers)
                            with open(destino, "wb") as f:
                                f.write(r.content)
                            print(f"✅ PDF guardado en: {destino}")
                        except Exception as e:
                            print(f"❌ Error al descargar desde {href}: {e}")
            except Exception as e:
                continue
    finally:
        driver.quit()

def guardar_resumen_en_txt(licitacion, texto, tipo):
    from pathlib import Path
    carpeta = Path(licitacion.GetAdministratives() or licitacion.GetTecniques()).parent
    nombre_archivo = f"resumen_{tipo}.txt"
    ruta_resumen = carpeta / nombre_archivo

    with open(ruta_resumen, "w", encoding="utf-8") as f:
        f.write(texto)

    if tipo == "administrativo":
        licitacion.SetResumenAdministrativo(str(ruta_resumen))
    elif tipo == "tecnico":
        licitacion.SetResumenTecnico(str(ruta_resumen))
    elif tipo == "sintesis":
        licitacion.SetSintesis(str(ruta_resumen))

def guardar_licitaciones_csv(licitaciones, ruta_archivo="licitaciones.csv"):
    with open(ruta_archivo, mode="w", newline="", encoding="utf-8") as archivo:
        writer = csv.writer(archivo)
        writer.writerow([
            "Empleador", "Titulo", "Enlace", "FechaPublicacion",
            "FechaLimite", "Presupuesto", "Administratives", "Tecniques"
        ])
        for lic in licitaciones:
            writer.writerow([
                lic.GetEmpleador(),
                lic.GetTitulo(),
                lic.GetEnlace(),
                lic.GetFecha_publicacion(),
                lic.GetFecha_limite(),
                lic.GetPresupuesto(),
                lic.GetAdministratives(),
                lic.GetTecniques(),
            ])

def cargar_licitaciones_csv(ruta_archivo="licitaciones.csv"):
    licitaciones = []
    with open(ruta_archivo, mode="r", encoding="utf-8") as archivo:
        reader = csv.DictReader(archivo)
        for fila in reader:
            lic = Licitacion(
                fila["Empleador"],
                fila["Titulo"],
                fila["Enlace"],
                fila["FechaPublicacion"],
                fila["FechaLimite"],
                fila["Presupuesto"],
                fila.get("Administratives", "").strip() or None,
                fila.get("Tecniques", "").strip() or None
            )
            licitaciones.append(lic)
    return licitaciones

def main():

    csv_path = "licitaciones.csv"
    licitaciones_guardadas = []

    respuesta = input("¿Quieres cargar las licitaciones desde archivo CSV? (y/n): ").strip().lower()

    if respuesta == "y" and os.path.exists(csv_path):
        licitaciones_guardadas = cargar_licitaciones_csv(csv_path)
        print(f" {len(licitaciones_guardadas)} licitaciones cargadas desde {csv_path}")
    else:
        print(" Se continuará con el proceso normal (descarga desde correo y scrapping).")

    # Encontrar el correo
    mail = connect_to_email()
    mensaje = buscar_correo_por_asunto(mail, asunto)
    mail.logout()
    if not mensaje:
        print("❌ No se encontró ningún correo reciente con ese asunto.")
        return
    #Convertir las licitaciones del correo en objetos licitacion
    html = extraer_html_del_mensaje(mensaje)
    if not html:
        print("⚠️ No se pudo extraer HTML del correo.")
        return

    licitaciones_extraidas = extraer_licitaciones_desde_html(html)
    print(f"\n📋 Se detectaron {len(licitaciones_extraidas)} licitaciones del correo")

    # Ignorar las cargadas del csv
    enlaces_existentes = {l.GetEnlace() for l in licitaciones_guardadas}
    nuevas_licitaciones = [
        l for l in licitaciones_extraidas if l.GetEnlace() not in enlaces_existentes
    ]
    print(f"📥 Nuevas licitaciones detectadas: {len(nuevas_licitaciones)}")

    #Descarta las que no cumplas ciertos requisitos
    licitaciones_filtradas = filtrado_inicial(nuevas_licitaciones)
    prompts = cargar_prompts_desde_txt()
    print(f"\n📋 Se conservan {len(licitaciones_filtradas)} licitaciones después del primer filtrado")
    licitaciones_filtradas = filtrar_por_tematicas(licitaciones_filtradas, prompts)
    print(f"\n📋 Se conservan {len(licitaciones_filtradas)} licitaciones después del segundo filtrado")
    print(f"\n Descargando los pdfs administrativos y técnicos de la pagina web")
    # Scrapping de las restantes
    for lic in licitaciones_filtradas:
        if lic.GetAdministratives() and os.path.exists(lic.GetAdministratives()) and \
                lic.GetTecniques() and os.path.exists(lic.GetTecniques()):
            print(f" Ya existen los PDF para: {lic.GetTitulo()}")
            continue

        try:
            descargar_pdfs_por_href(lic)
        except Exception as e:
            print(f"❌ Error al procesar licitación: {lic.GetTitulo()} — {e}")

    todas_licitaciones = licitaciones_guardadas + licitaciones_filtradas

    respuesta = input("¿Quieres guardar las licitaciones en un archivo CSV? (y/n): ").strip().lower()

    if respuesta == "y" and os.path.exists(csv_path):
        guardar_licitaciones_csv(todas_licitaciones, csv_path)
        print(f"✅ Datos guardados en {csv_path}")
    else:
        print(f"✅ No se guardará este resultado")


    prompts = cargar_prompts_desde_txt()
    for lic in todas_licitaciones:
        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")

        # Requisitos Administrativos
        ruta_admin = lic.GetResumenAdministrativo()
        if ruta_admin and os.path.exists(ruta_admin):
            print("📄 Ya existe el resumen administrativo, se omite.")
        else:
            resultado_admin = openAIRequest(lic, "requisitos_administrativos", prompts)
            guardar_resumen_en_txt(lic, resultado_admin, "administrativo")
            print("✅ Resumen administrativo generado y guardado.")

        # Requisitos Técnicos
        ruta_tec = lic.GetResumenTecnico()
        if ruta_tec and os.path.exists(ruta_tec):
            print("📄 Ya existe el resumen técnico, se omite.")
        else:
            resultado_tec = openAIRequest(lic, "requisitos_tecnicos", prompts)
            guardar_resumen_en_txt(lic, resultado_tec, "tecnico")
            print("✅ Resumen técnico generado y guardado.")

        # Síntesis Combinada
        ruta_sintesis = lic.GetSintesis()
        if ruta_sintesis and os.path.exists(ruta_sintesis):
            print("📄 Ya existe la síntesis, se omite.")
        else:
            resultado_sintesis = openAIRequest(lic, "sintesis_requisitos", prompts)
            guardar_resumen_en_txt(lic, resultado_sintesis, "sintesis")
            print("✅ Síntesis generada y guardada.")


if __name__ == "__main__":
    main()