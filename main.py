import csv
import email
import sys
from pathlib import Path
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
diasLimite=1 #26                                       #Plazo para hacer la licitación mínimo
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
                continue

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
                            licitacion.SetPDFAdministrativo(destino)
                        elif "tècniques" in label_text:
                            licitacion.SetPDFTecnico(destino)

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
    carpeta = Path(licitacion.GetPDFAdministrativo() or licitacion.GetPDFTecnico()).parent
    nombre_archivo = f"resumen_{tipo}.txt"
    ruta_resumen = carpeta / nombre_archivo

    with open(ruta_resumen, "w", encoding="utf-8") as f:
        f.write(texto)

    if tipo == "administrativo":
        licitacion.SetResumenAdministrativo(str(ruta_resumen))
    elif tipo == "tecnico":
        licitacion.SetResumenTecnico(str(ruta_resumen))
    elif tipo == "sintesis":
        licitacion.SetSintesisRequisitos(str(ruta_resumen))

def guardar_licitaciones_csv(licitaciones, ruta_archivo="licitaciones.csv"):
    from pathlib import Path
    ruta = Path(ruta_archivo).resolve()
    os.makedirs(ruta.parent, exist_ok=True)

    try:
        with open(ruta, mode="w", newline="", encoding="utf-8") as archivo:
            writer = csv.writer(archivo)
            writer.writerow([
                "Empleador", "Titulo", "Enlace", "FechaPublicacion",
                "FechaLimite", "Presupuesto", "PDFAdministrativo", "PDFTecnico",
                "ResumenAdministrativo", "ResumenTecnico", "SintesisRequisitos"
            ])
            for lic in licitaciones:
                writer.writerow([
                    lic.GetEmpleador(),
                    lic.GetTitulo(),
                    lic.GetEnlace(),
                    lic.GetFecha_publicacion(),
                    lic.GetFecha_limite(),
                    lic.GetPresupuesto(),
                    lic.GetPDFAdministrativo(),
                    lic.GetPDFTecnico(),
                    lic.GetResumenAdministrativo(),
                    lic.GetResumenTecnico(),
                    lic.GetSintesisRequisitos()
                ])

        print(f"✅ CSV guardado en: {ruta}")
    except Exception as e:
        print(f"❌ Error al guardar CSV en {ruta}: {e}")

def cargar_licitaciones_csv(ruta_archivo="licitaciones.csv"):
    licitaciones = []
    with open(ruta_archivo, mode="r", encoding="utf-8") as archivo:
        reader = csv.DictReader(archivo)
        for fila in reader:
            lic = Licitacion(
                empleador=fila["Empleador"],
                titulo=fila["Titulo"],
                enlace=fila["Enlace"],
                fecha_publicacion=fila["FechaPublicacion"],
                fecha_limite=fila["FechaLimite"],
                presupuesto=fila["Presupuesto"]
            )

            # Asignar documentos opcionales si existen
            lic.SetPDFAdministrativo(fila.get("PDFAdministrativo", "").strip())
            lic.SetPDFTecnico(fila.get("PDFTecnico", "").strip())
            lic.SetResumenAdministrativo(fila.get("ResumenAdministrativo", "").strip())
            lic.SetResumenTecnico(fila.get("ResumenTecnico", "").strip())
            lic.SetSintesisRequisitos(fila.get("SintesisRequisitos", "").strip())
            lic.SetIntroduccionOferta(fila.get("IntroduccionOferta", "").strip())
            lic.SetMemoriaTecnica(fila.get("MemoriaTecnica", "").strip())
            lic.SetCriteriosSocialesMedioambientales(fila.get("CriteriosSocialesMedioambientales", "").strip())
            lic.SetPropuestaEconomica(fila.get("PropuestaEconomica", "").strip())
            lic.SetDocumentacionAdministrativaSolvencia(fila.get("DocumentacionAdministrativaSolvencia", "").strip())

            licitaciones.append(lic)
    return licitaciones

def seleccionar_licitaciones_manualmente(licitaciones_extraidas, csv_path):
    seleccionadas = []
    while True:
        print("\n📋 Licitaciones disponibles:")
        for idx, lic in enumerate(licitaciones_extraidas, start=1):
            print(f"{idx}. {lic.GetTitulo()}")

        seleccion = input("Escribe el número de la licitación a añadir (o 'q' para salir): ").strip().lower()
        if seleccion == "q":
            break

        try:
            idx = int(seleccion) - 1
            if 0 <= idx < len(licitaciones_extraidas):
                seleccionadas.append(licitaciones_extraidas[idx])
                print(f"✅ Añadida: {licitaciones_extraidas[idx].GetTitulo()}")
            else:
                print("❌ Número fuera de rango.")
        except ValueError:
            print("⚠️ Entrada no válida. Escribe un número o 'q'.")

    if seleccionadas:
        guardar_licitaciones_csv_con_check(seleccionadas, csv_path)
        print(f"✅ {len(seleccionadas)} licitaciones guardadas en {csv_path}")
    else:
        print("📂 No se añadieron licitaciones.")

def scrapping_de_pdfs(licitaciones):
    print(f"\n Descargando los pdfs administrativos y técnicos de la pagina web")
    # Scrapping de la web para obtener PDFS
    for lic in licitaciones:
        if lic.GetPDFAdministrativo() and os.path.exists(lic.GetPDFAdministrativo()) and \
                lic.GetPDFTecnico() and os.path.exists(lic.GetPDFTecnico()):
            print(f" Ya existen los PDF para: {lic.GetTitulo()}")
            continue
        try:
            descargar_pdfs_por_href(lic)
        except Exception as e:
            print(f"❌ Error al procesar licitación: {lic.GetTitulo()} — {e}")

def pedir_documentacion(lic, tipo):

    #Tipo: adminsitrativo, tecnico, sintesis
    match tipo:
        case "administrativo":
            ruta = lic.GetResumenAdministrativo()
            tipo_prompt="requisitos_administrativos"
        case "tecnico":
            ruta = lic.GetResumenTecnico()
            tipo_prompt = "requisitos_tecnicos"
        case "sintesis":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "sintesis_requisitos"
        case "introduccion":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "introduccion"
        case "memoria tecnica":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "memoria_tecnica"
        case "social/medioambiental":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "social_medioambiental"
        case "propuesta economica":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "propuesta_economica"
        case "administrativa/solvencia":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "administrativa_solvencia"
        case _:
            print("Otro")#TODO implementar

    prompts = cargar_prompts_desde_txt()
    print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")

    # Omitir si ya existe
    if ruta and os.path.exists(ruta):
        print("📄 Ya existe el documento "+tipo+", se omite.")
    else:
        #Request a la API
        resultado = openAIRequest(lic, tipo_prompt, prompts)
        guardar_resumen_en_txt(lic, resultado, tipo)
        print("✅ Documento"+tipo+" generado y guardado.")


def silenciar_prints(func, *args, **kwargs):
    """Ejecuta func en silencio"""
    original_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')  # Redirige prints a /dev/null
    try:
        result = func(*args, **kwargs)
    finally:
        sys.stdout.close()
        sys.stdout = original_stdout  # Restaura salida normal
    return result

def guardar_licitaciones_csv_con_check(licitaciones, ruta_archivo="licitaciones.csv"):
    ruta = Path(ruta_archivo)
    if ruta.exists():
        print(f"⚠️ El archivo {ruta_archivo} ya existe.")
        decision = input("¿Quieres sobrescribirlo (1), añadir nuevas licitaciones al documento(2) o cancelar (3)? [1/2/3]: ").strip().lower()

        if decision == "3":
            print("❌ Operación cancelada. No se ha guardado nada.")
            return
        elif decision == "2":
            print("➕ Añadiendo nuevas licitaciones al archivo existente...")
            licitaciones_existentes = cargar_licitaciones_csv(ruta_archivo)

            # Evitar duplicados usando los enlaces como identificador único
            enlaces_existentes = {lic.GetEnlace() for lic in licitaciones_existentes}
            nuevas_licitaciones = [lic for lic in licitaciones if lic.GetEnlace() not in enlaces_existentes]

            print(f"📥 Nuevas licitaciones detectadas: {len(nuevas_licitaciones)}")

            licitaciones_combinadas = licitaciones_existentes + nuevas_licitaciones
            guardar_licitaciones_csv(licitaciones_combinadas, ruta_archivo)
            print(f"✅ Archivo actualizado con {len(licitaciones_combinadas)} licitaciones en total.")
            return
        elif decision == "1":
            guardar_licitaciones_csv(licitaciones, ruta_archivo)
            print(f"✅ Archivo guardado: {ruta_archivo}")
            return
        else:
            print("⚠️ Opción no válida. Operación cancelada.")
            return
    else:
        guardar_licitaciones_csv(licitaciones, ruta_archivo)
        print(f"✅ Archivo creado: {ruta_archivo}")


def main():

    csv_path = csv_path = Path(__file__).parent / "licitaciones.csv"

    licitaciones_guardadas = []

    respuesta = input("¿Quieres buscar nuevas licitaciones (1) o trabajar con las que ya tienes en tu archivo (2)? (1/2): ").strip().lower()

    if respuesta == "2" and not os.path.exists(csv_path):
        print(f" Genera antes un archivo con las licitaciones con las cuales quieres trabajar")
    elif respuesta == "2" and os.path.exists(csv_path):
        licitaciones_guardadas = cargar_licitaciones_csv(csv_path)
        print(f" {len(licitaciones_guardadas)} licitaciones cargadas desde {csv_path}")

        accion = input("""
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            📂 ¿Qué archivos quieres generar? (Introduce el número)
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
              1️⃣  Generar todos los documentos
              2️⃣  Descargar los plecs administrativos y técnicos
              3️⃣  Resumir los plecs administrativos y técnicos
              4️⃣  Crear una síntesis de los requisitos
              5️⃣  Redactar la introducción de la oferta
              6️⃣  Elaborar la memoria técnica
              7️⃣  Desarrollar los criterios sociales y medioambientales
              8️⃣  Preparar la propuesta económica
              9️⃣  Compilar documentación administrativa y de solvencia
             🔟  Cambiar de licitación o grupo de licitaciones
            
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            """)

        match accion:
            case '1':
                scrapping_de_pdfs(licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    pedir_documentacion(lic, "administrativo")
                    pedir_documentacion(lic, "tecnico")
                    pedir_documentacion(lic, "sintesis")
                    pedir_documentacion(lic, "introduccion")
                    pedir_documentacion(lic, "memoria tecnica")
                    pedir_documentacion(lic, "social_medioambiental")
                    pedir_documentacion(lic, "propuesta_economica")
                    pedir_documentacion(lic, "administrativa_solvencia")

            case '2':
                scrapping_de_pdfs(licitaciones_guardadas)

            case '3':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                print("Pasos previos completados")
                for lic in licitaciones_guardadas:
                    pedir_documentacion(lic, "administrativo")
                    pedir_documentacion(lic, "tecnico")

            case '4':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    silenciar_prints(pedir_documentacion(lic, "adminsitrativo"))
                    silenciar_prints(pedir_documentacion(lic, "tecnico"))
                    pedir_documentacion(lic, "sintesis")

            case '5':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    silenciar_prints(pedir_documentacion(lic, "adminsitrativo"))
                    silenciar_prints(pedir_documentacion(lic, "tecnico"))
                    silenciar_prints(pedir_documentacion(lic, "sintesis"))
                    pedir_documentacion(lic,"introduccion")
            case '6':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    silenciar_prints(pedir_documentacion(lic, "adminsitrativo"))
                    silenciar_prints(pedir_documentacion(lic, "tecnico"))
                    silenciar_prints(pedir_documentacion(lic, "sintesis"))
                    pedir_documentacion(lic, "memoria tecnica")
            case '7':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    silenciar_prints(pedir_documentacion(lic, "adminsitrativo"))
                    silenciar_prints(pedir_documentacion(lic, "tecnico"))
                    silenciar_prints(pedir_documentacion(lic, "sintesis"))
                    pedir_documentacion(lic, "social_medioambiental")
            case '8':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    silenciar_prints(pedir_documentacion(lic, "adminsitrativo"))
                    silenciar_prints(pedir_documentacion(lic, "tecnico"))
                    silenciar_prints(pedir_documentacion(lic, "sintesis"))
                    pedir_documentacion(lic, "propuesta_economica")
            case '9':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    silenciar_prints(pedir_documentacion(lic, "adminsitrativo"))
                    silenciar_prints(pedir_documentacion(lic, "tecnico"))
                    silenciar_prints(pedir_documentacion(lic, "sintesis"))
                    pedir_documentacion(lic, "administrativa_solvencia")
            case'10':
                print("Iniciando pasos previos para cumplir tu peticion")
                silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                for lic in licitaciones_guardadas:
                    pedir_documentacion(lic, "adminsitrativo")
                    pedir_documentacion(lic, "tecnico")
                    pedir_documentacion(lic, "sintesis")
                    pedir_documentacion(lic, "introduccion")
            case _:
                print("No te he entendido, di de nuevo el numero de documento que necesitas")#TODO implementar


        guardar_licitaciones_csv(licitaciones_guardadas, csv_path)
        print(f"✅ Datos actualizados en {csv_path}")

        print(
            "Acuerdate de revisar tus documentos en la carpeta de licitaciones, y si quieres continuar carga "+{csv_path}+
            "\n Recuerda que estos documentos estan generados automaticamente, asi que pueden requerir revision humana antes de usarlos para algun tramite importante")

    elif respuesta=="1":
        print(" Se descargarán desde el correo las licitaciones que se adecuen.")

        # Encontrar el correo
        mail = connect_to_email()
        mensaje = buscar_correo_por_asunto(mail, asunto)
        mail.logout()
        if not mensaje:
            print("❌ No se encontró ningún correo reciente con ese asunto.")
            return
        # Convertir las licitaciones del correo en objetos licitacion
        html = extraer_html_del_mensaje(mensaje)
        if not html:
            print("⚠️ No se pudo extraer HTML del correo.")
            return

        licitaciones_extraidas = extraer_licitaciones_desde_html(html)
        print(f"\n📋 Se detectaron {len(licitaciones_extraidas)} licitaciones del correo")

        respuesta = input(
            "¿Quieres que se escoja automáticamente las licitaciones que te interesan mediante las características definidas (1) o quieres escoger a mano (2)? (1/2): "
        ).strip()

        if respuesta == "1":
            licitaciones_filtradas = filtrado_inicial(licitaciones_extraidas)
            prompts = cargar_prompts_desde_txt()
            print(
                f"\n📋 Se conservan {len(licitaciones_filtradas)} licitaciones después del primer filtrado (precios y fechas)")
            licitaciones_filtradas = filtrar_por_tematicas(licitaciones_filtradas, prompts)
            print(
                f"\n📋 Se conservan {len(licitaciones_filtradas)} licitaciones después del segundo filtrado (temáticas)")

            guardar_licitaciones_csv_con_check(licitaciones_filtradas, csv_path)
            print(f"✅ Datos actualizados en {csv_path}")

            for lic in licitaciones_filtradas:
                print(f"✅ {lic.GetTitulo()}")

            respuesta = input("¿Quieres escoger manualmente alguna más? (y/n): ").strip().lower()
            if respuesta == "y":
                seleccionar_licitaciones_manualmente(licitaciones_extraidas, csv_path)
            else:
                print("👋 Proceso completado.")
                guardar_licitaciones_csv(licitaciones_filtradas,csv_path)
                return

        elif respuesta == "2":
            seleccionar_licitaciones_manualmente(licitaciones_extraidas, csv_path)

        else:
            print("⚠️ Opción no reconocida. Cancelando.")
    else:
        print("⚠️ Opción no reconocida. Cancelando.")


if __name__ == "__main__":
    main()