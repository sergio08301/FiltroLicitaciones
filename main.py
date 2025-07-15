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
from pdf_analisis import openAIRequest, cargar_prompts_desde_txt, filtrar_por_tematicas, guardar_consumo
from dataclasses import dataclass
import sys
import io

# Configuración (Cargar variables de entorno (.env))
load_dotenv()
dias = int(os.getenv("dias", 30))  # valor por defecto 30 si no está en .env
presupuestoLimite = float(os.getenv("presupuestoLimite", 500000))
diasLimite = int(os.getenv("diasLimite", 3))
asunto = os.getenv("asunto", "Correu diari de subscriptors generals")
colorEmpleador = os.getenv("colorEmpleador", "#660303")
csv_path = os.getenv("csv_path", "licitaciones.csv")
# ruta_csv = "licitaciones.csv"
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# Cambia este si usas otro proveedor de correo
IMAP_SERVER = "imap.gmail.com"


def connect_to_email():
    print("Conectando al correo...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("inbox")
    return mail


def buscar_correo_por_asunto(mail):
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
        print("Mensaje a analizar: " + subject)

        if subject and asunto.lower() in subject.lower():
            print("\n✅ Correo encontrado:")
            print("Asunto:", subject)
            fecha_raw = message["Date"]
            fecha_formateada = parsedate_to_datetime(fecha_raw).strftime('%d/%m/%Y')  # formatear la fecha
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


def descargar_pdfs_por_href(licitacion, carpeta_base="documentacion"):
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

                            actualizar_licitacion_en_csv(licitacion, csv_path)
                        except Exception as e:
                            print(f"❌ Error al descargar desde {href}: {e}")
            except Exception as e:
                continue
    finally:
        driver.quit()


def guardar_licitaciones_csv(licitaciones, ruta_archivo="licitaciones.csv"):
    from pathlib import Path
    ruta = Path(ruta_archivo).resolve()
    os.makedirs(ruta.parent, exist_ok=True)

    # 🧹 Limpiar carpetas de licitaciones no presentes
    carpeta_pdfs = Path("documentacion").resolve()
    if carpeta_pdfs.exists():
        carpetas_existentes = [d for d in carpeta_pdfs.iterdir() if d.is_dir()]
        titulos_actuales = {limpiar_nombre(lic.GetTitulo()) for lic in licitaciones}

        for carpeta in carpetas_existentes:
            if carpeta.name not in titulos_actuales:
                try:
                    shutil.rmtree(carpeta)
                    print(f"🗑️ Carpeta eliminada: {carpeta}")
                except Exception as e:
                    print(f"⚠️ No se pudo eliminar {carpeta}: {e}")
    try:
        with open(ruta, mode="w", newline="", encoding="utf-8-sig") as archivo:
            writer = csv.writer(archivo)
            writer.writerow([
                "Empleador", "Titulo", "Enlace", "FechaPublicacion",
                "FechaLimite", "Presupuesto", "PDFAdministrativo", "PDFTecnico",
                "ResumenAdministrativo", "ResumenTecnico", "SintesisRequisitos",
                "IntroduccionOferta", "MemoriaTecnica", "CriteriosSocialesMedioambientales",
                "PropuestaEconomica", "DocumentacionAdministrativaSolvencia"
            ])
            for lic in licitaciones:
                writer.writerow([
                    safe_text(lic.GetEmpleador()),
                    safe_text(lic.GetTitulo()),
                    safe_text(lic.GetEnlace()),
                    safe_text(lic.GetFecha_publicacion()),
                    safe_text(lic.GetFecha_limite()),
                    safe_text(lic.GetPresupuesto()),
                    safe_text(lic.GetPDFAdministrativo()),
                    safe_text(lic.GetPDFTecnico()),
                    safe_text(lic.GetResumenAdministrativo()),
                    safe_text(lic.GetResumenTecnico()),
                    safe_text(lic.GetSintesisRequisitos()),
                    safe_text(lic.GetIntroduccionOferta()),
                    safe_text(lic.GetMemoriaTecnica()),
                    safe_text(lic.GetCriteriosSocialesMedioambientales()),
                    safe_text(lic.GetPropuestaEconomica()),
                    safe_text(lic.GetDocumentacionAdministrativaSolvencia())
                ])

        print(f"✅ CSV guardado en: {ruta}")
    except Exception as e:
        print(f"❌ Error al guardar CSV en {ruta}: {e}")


def guardar_resumen_en_txt(licitacion, texto, tipo):
    if texto.strip().startswith("❌"):
        print(f"⚠️ No se guarda '{tipo}' porque contiene un error: {texto.strip()[:80]}...")
        return

    carpeta_base = Path(licitacion.GetPDFAdministrativo() or licitacion.GetPDFTecnico())
    if not carpeta_base or not carpeta_base.exists():
        raise ValueError("❌ No se encontró ninguna carpeta base para guardar el resumen.")
    carpeta = carpeta_base.parent

    # 📄 Crear el nombre del archivo
    nombre_archivo = f"{tipo}.txt"
    ruta = carpeta / nombre_archivo

    # 📝 Guardar el texto en el archivo
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)

    # 🔗 Asociar el resumen al atributo correcto en la licitación
    tipo = tipo.lower()
    if tipo == "administrativo":
        licitacion.SetResumenAdministrativo(str(ruta))
    elif tipo == "tecnico":
        licitacion.SetResumenTecnico(str(ruta))
    elif tipo == "sintesis":
        licitacion.SetSintesisRequisitos(str(ruta))
    elif tipo == "introduccion":
        licitacion.SetIntroduccionOferta(str(ruta))
    elif tipo == "memoria_tecnica":
        licitacion.SetMemoriaTecnica(str(ruta))
    elif tipo == "social_medioambiental":
        licitacion.SetCriteriosSocialesMedioambientales(str(ruta))
    elif tipo == "propuesta_economica":
        licitacion.SetPropuestaEconomica(str(ruta))
    elif tipo == "administrativa_solvencia":
        licitacion.SetDocumentacionAdministrativaSolvencia(str(ruta))
    else:
        print(f"⚠️ Tipo de resumen desconocido: {tipo}. Archivo guardado pero no asociado a la licitación.")
        return

    print("✅ Documento " + tipo + " generado y guardado en el documento csv.")

    actualizar_licitacion_en_csv(licitacion, csv_path)


def actualizar_licitacion_en_csv(licitacion, ruta_archivo="licitaciones.csv"):
    try:
        licitaciones = []
        # Leer CSV existente si existe
        if os.path.exists(ruta_archivo):
            licitaciones = cargar_licitaciones_csv(ruta_archivo)

        # Reemplazar o añadir
        enlaces_existentes = {l.GetEnlace(): l for l in licitaciones}
        enlaces_existentes[licitacion.GetEnlace()] = licitacion  # Actualiza o añade

        # Guardar todas las licitaciones de nuevo
        silenciar_prints(guardar_licitaciones_csv, list(enlaces_existentes.values()), ruta_archivo)
        print(f"✅ CSV actualizado con: {safe_text(licitacion.GetTitulo())}")
    except Exception as e:
        print(f"")  # TODO esto es una chapuza, si quito esto explota en un montón de errores, si lo dejo funciona bien


def safe_text(text):
    """Limpia el texto para evitar caracteres no ASCII que rompen CSV en Windows."""
    if not text:
        return ""
    try:
        return text.encode("ascii", "ignore").decode("ascii")
    except Exception:
        return str(text)


def cargar_licitaciones_csv(ruta_archivo="licitaciones.csv"):
    licitaciones = []
    with open(ruta_archivo, mode="r", encoding="utf-8-sig") as archivo:
        reader = csv.DictReader(archivo)
        if "Empleador" not in reader.fieldnames:
            raise ValueError(f"❌ El CSV {ruta_archivo} no tiene cabeceras correctas: {reader.fieldnames}")

        for fila in reader:
            lic = Licitacion(
                empleador=fila.get("Empleador", ""),
                titulo=fila.get("Titulo", ""),
                enlace=fila.get("Enlace", ""),
                fecha_publicacion=fila.get("FechaPublicacion", ""),
                fecha_limite=fila.get("FechaLimite", ""),
                presupuesto=fila.get("Presupuesto", "")
            )

            lic.SetPDFAdministrativo(fila.get("PDFAdministrativo", ""))
            lic.SetPDFTecnico(fila.get("PDFTecnico", ""))
            lic.SetResumenAdministrativo(fila.get("ResumenAdministrativo", ""))
            lic.SetResumenTecnico(fila.get("ResumenTecnico", ""))
            lic.SetSintesisRequisitos(fila.get("SintesisRequisitos", ""))
            lic.SetIntroduccionOferta(fila.get("IntroduccionOferta", ""))
            lic.SetMemoriaTecnica(fila.get("MemoriaTecnica", ""))
            lic.SetCriteriosSocialesMedioambientales(fila.get("CriteriosSocialesMedioambientales", ""))
            lic.SetPropuestaEconomica(fila.get("PropuestaEconomica", ""))
            lic.SetDocumentacionAdministrativaSolvencia(fila.get("DocumentacionAdministrativaSolvencia", ""))

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
    match tipo:
        case "administrativo":
            ruta = lic.GetResumenAdministrativo()
            tipo_prompt = "requisitos_administrativos"
        case "tecnico":
            ruta = lic.GetResumenTecnico()
            tipo_prompt = "requisitos_tecnicos"
        case "sintesis":
            ruta = lic.GetSintesisRequisitos()
            tipo_prompt = "sintesis_requisitos"
        case "introduccion":
            ruta = lic.GetIntroduccionOferta()
            tipo_prompt = "introduccion"
        case "memoria_tecnica":
            ruta = lic.GetMemoriaTecnica()
            tipo_prompt = "memoria_tecnica"
        case "social_medioambiental":
            ruta = lic.GetCriteriosSocialesMedioambientales()
            tipo_prompt = "social_medioambiental"
        case "propuesta_economica":
            ruta = lic.GetPropuestaEconomica()
            tipo_prompt = "propuesta_economica"
        case "administrativa_solvencia":
            ruta = lic.GetDocumentacionAdministrativaSolvencia()
            tipo_prompt = "administrativa_solvencia"
        case _:
            print("Tipo de texto no reconocido")
            sys.exit(0)

    prompts = cargar_prompts_desde_txt()

    # Omitir si ya existe
    if ruta and os.path.exists(ruta):
        print(" Ya existe el documento " + tipo + ", se omite.")
        time.sleep(1)
    else:
        # Request a la API
        resultado = openAIRequest(lic, tipo_prompt, prompts)
        guardar_resumen_en_txt(lic, resultado, tipo)


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

def eliminar_licitaciones(csv_path="licitaciones.csv"):
    if not os.path.exists(csv_path):
        print("❌ No se encontró el archivo CSV.")
        return

    licitaciones = cargar_licitaciones_csv(csv_path)
    if not licitaciones:
        print("⚠️ No hay licitaciones en el archivo CSV.")
        return

    while True:
        print("\n📋 Licitaciones actuales en el archivo:")
        for idx, lic in enumerate(licitaciones, start=1):
            print(f"{idx}. {lic.GetTitulo()}")

        seleccion = input(
            "\nEscribe el número de la licitación a gestionar (o 'all' para gestionar todas, o 'q' para salir): "
        ).strip().lower()

        if seleccion == "q":
            print("❌ Operación cancelada.")
            return

        if seleccion == "all":
            indices_a_gestionar = list(range(len(licitaciones)))
        else:
            try:
                indices_a_gestionar = [int(i) - 1 for i in seleccion.split(",") if i.strip().isdigit()]
                indices_a_gestionar = [i for i in indices_a_gestionar if 0 <= i < len(licitaciones)]
            except ValueError:
                print("⚠️ Entrada no válida.")
                continue

            if not indices_a_gestionar:
                print("⚠️ No se seleccionó ninguna licitación válida.")
                continue

        nuevas_licitaciones = licitaciones.copy()
        for idx in sorted(indices_a_gestionar, reverse=True):
            lic = licitaciones[idx]
            print("\n📝 Detalle de la licitación seleccionada:")
            print(lic.to_print())

            accion = input(
                "\n¿Qué quieres hacer con esta licitación?\n"
                "1️⃣ Eliminar del CSV\n"
                "2️⃣ Resetear campos y borrar archivos de la carpeta\n"
                "3️⃣ Omitir (no hacer nada)\n"
                "Selecciona (1/2/3): "
            ).strip()

            if accion == "1":
                print("uno")

            elif accion == "2":
                # Resetear campos de documentos/resúmenes
                print(f"🔄 Reseteando campos y borrando archivos de: {lic.GetTitulo()}")
                lic.SetPDFAdministrativo("")
                lic.SetPDFTecnico("")
                lic.SetResumenAdministrativo("")
                lic.SetResumenTecnico("")
                lic.SetSintesisRequisitos("")
                lic.SetIntroduccionOferta("")
                lic.SetMemoriaTecnica("")
                lic.SetCriteriosSocialesMedioambientales("")
                lic.SetPropuestaEconomica("")
                lic.SetDocumentacionAdministrativaSolvencia("")


            elif accion == "3":
                print("⏭️ Se omite esta licitación.")
                continue
            else:
                print("⚠️ Opción no válida. Se omite esta licitación.")

        guardar_licitaciones_csv(nuevas_licitaciones, csv_path)
        print(f"✅ CSV actualizado: {len(nuevas_licitaciones)} licitaciones restantes.")

        continuar = input("\n¿Quieres gestionar más licitaciones? (y/n): ").strip().lower()
        if continuar != "y":
            break

def guardar_licitaciones_csv_con_check(licitaciones, ruta_archivo="licitaciones.csv"):
    ruta = Path(ruta_archivo)
    if ruta.exists():
        print(f"⚠️ El archivo {ruta_archivo} ya existe.")
        decision = input(
            "¿Quieres sobrescribirlo (1), añadir nuevas licitaciones al documento(2) o cancelar (3)? [1/2/3]: ").strip().lower()

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
            return
        else:
            print("⚠️ Opción no válida. Operación cancelada.")
            return
    else:
        guardar_licitaciones_csv(licitaciones, ruta_archivo)


def main():
    licitaciones_guardadas = []

    respuesta = input(
        "¿Quieres editar las selección de licitaciones (1) o trabajar con las que ya tienes en tu archivo (2)? (1/2): ").strip().lower()

    if respuesta == "2" and not os.path.exists(csv_path):
        print(f" Genera antes un archivo con las licitaciones con las cuales quieres trabajar")
    elif respuesta == "2" and os.path.exists(csv_path):
        while True:
            licitaciones_guardadas = cargar_licitaciones_csv(csv_path)

            accion = input(f"""
                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                Se han cargado {len(licitaciones_guardadas)} licitación(es), ¿qué quieres hacer?
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
                 🔟  Salir del programa

                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                """)

            match accion:
                case '1':
                    scrapping_de_pdfs(licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        pedir_documentacion(lic, "administrativo")
                        pedir_documentacion(lic, "tecnico")
                        pedir_documentacion(lic, "sintesis")
                        pedir_documentacion(lic, "introduccion")
                        pedir_documentacion(lic, "memoria_tecnica")
                        pedir_documentacion(lic, "social_medioambiental")
                        pedir_documentacion(lic, "propuesta_economica")
                        pedir_documentacion(lic, "administrativa_solvencia")

                case '2':
                    scrapping_de_pdfs(licitaciones_guardadas)

                case '3':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        pedir_documentacion(lic, "administrativo")
                        pedir_documentacion(lic, "tecnico")

                case '4':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        silenciar_prints(pedir_documentacion, lic, "administrativo")
                        silenciar_prints(pedir_documentacion, lic, "tecnico")
                        pedir_documentacion(lic, "sintesis")

                case '5':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        silenciar_prints(pedir_documentacion, lic, "administrativo")
                        silenciar_prints(pedir_documentacion, lic, "tecnico")
                        silenciar_prints(pedir_documentacion, lic, "sintesis")
                        pedir_documentacion(lic, "introduccion")
                case '6':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        silenciar_prints(pedir_documentacion, lic, "administrativo")
                        silenciar_prints(pedir_documentacion, lic, "tecnico")
                        silenciar_prints(pedir_documentacion, lic, "sintesis")
                        pedir_documentacion(lic, "memoria tecnica")
                case '7':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        silenciar_prints(pedir_documentacion, lic, "administrativo")
                        silenciar_prints(pedir_documentacion, lic, "tecnico")
                        silenciar_prints(pedir_documentacion, lic, "sintesis")
                        pedir_documentacion(lic, "social_medioambiental")
                case '8':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        silenciar_prints(pedir_documentacion, lic, "administrativo")
                        silenciar_prints(pedir_documentacion, lic, "tecnico")
                        silenciar_prints(pedir_documentacion, lic, "sintesis")
                        pedir_documentacion(lic, "propuesta_economica")
                case '9':
                    silenciar_prints(scrapping_de_pdfs, licitaciones_guardadas)
                    for lic in licitaciones_guardadas:
                        print(f"\n📝 Procesando licitación: {lic.GetTitulo()}")
                        silenciar_prints(pedir_documentacion, lic, "administrativo")
                        silenciar_prints(pedir_documentacion, lic, "tecnico")
                        silenciar_prints(pedir_documentacion, lic, "sintesis")
                        pedir_documentacion(lic, "administrativa_solvencia")
                case '10':
                    print("👋 Saliendo del programa. Hasta luego!")
                    sys.exit()
                case _:
                    print("No te he entendido, di de nuevo el numero de documento que necesitas")
                    continue

            print(f"✅ Datos actualizados en {csv_path}")

        print(
            f"Acuérdate de revisar tus documentos en la carpeta de licitaciones, y si quieres continuar carga {csv_path}"
            "\nRecuerda que estos documentos están generados automáticamente, así que pueden requerir revisión humana antes de usarlos para trámites importantes."
        )

    elif respuesta == "1":

        decision = input(
            "¿Seleccionar nuevas licitaciones en el correo (1) o editar las seleccionadas (2)? (1/2): ").strip().lower()

        if decision=="1":
            print(" Se descargarán las licitaciones desde tu correo")

            # Encontrar el correo
            mail = connect_to_email()
            mensaje = buscar_correo_por_asunto(mail)
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
                    guardar_licitaciones_csv(licitaciones_filtradas, csv_path)
                    return
            elif respuesta == "2":
                seleccionar_licitaciones_manualmente(licitaciones_extraidas, csv_path)
            else:
                print("⚠️ Opción no reconocida. Cancelando.")

        elif decision=="2":
            eliminar_licitaciones(csv_path)
        else:
            print("⚠️ Opción no reconocida. Cancelando.")
    else:
        print("⚠️ Opción no reconocida. Cancelando.")
    guardar_consumo()


if __name__ == "__main__":
    main()