import email
from dotenv import load_dotenv
import os
import imaplib
import re
from licitacion import Licitacion
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

#Configuración
dias= 3                                                 #dias que puede ir atrás en correo para buscar licitaciones
asunto= "Correu diari de subscriptors generals"         #Asunto que quieres buscar en los correos


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

def extraer_cuerpo_texto(mensaje):
    cuerpo = ""

    if mensaje.is_multipart():
        for part in mensaje.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    cuerpo += payload.decode(errors="ignore")
    else:
        payload = mensaje.get_payload(decode=True)
        if payload:
            cuerpo = payload.decode(errors="ignore")

    return cuerpo.strip()

def limpiar_cuerpo(cuerpo: str) -> str:
    # Definir marcadores
    inicio_clave = "Serveis"
    fin_clave = "Si voleu modificar la subscripció"

    # Encontrar índices
    inicio_idx = cuerpo.find(inicio_clave)
    fin_idx = cuerpo.find(fin_clave)

    # Si ambos marcadores existen, recortar entre ellos
    if inicio_idx != -1 and fin_idx != -1:
        # Excluir la frase de inicio sumando su longitud
        cuerpo_limpio = cuerpo[inicio_idx + len(inicio_clave):fin_idx].strip()
    else:
        cuerpo_limpio = cuerpo.strip()

    return cuerpo_limpio


import re
from licitacion import Licitacion


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

def main():
    mail = connect_to_email()
    mensaje = buscar_correo_por_asunto(mail, asunto)
    mail.logout()
    cuerpo = extraer_cuerpo_texto(mensaje)
    cuerpo_limpio = limpiar_cuerpo(cuerpo)
    print(cuerpo_limpio)
    #licitaciones = parsear_licitaciones(cuerpo_limpio)
    #print(f"\nSe encontraron {len(licitaciones)} licitaciones:\n")
    #for idx, lic in enumerate(licitaciones, 1):
    #    print(f"=== LICITACIÓN {idx} ===")
    #    print(lic.to_print())
    #    print("\n" + "=" * 50 + "\n")

if __name__ == "__main__":
    main()