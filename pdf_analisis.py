import os
from openai import OpenAI
import fitz  # PyMuPDF
import time
import os
import re
import fitz  # PyMuPDF
from dotenv import load_dotenv
import json
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()

# Inicializar cliente de OpenAI
client = OpenAI()

def cargar_prompts_desde_txt(ruta_carpeta="prompts") -> dict:
    prompts = {}
    for archivo in os.listdir(ruta_carpeta):
        if archivo.endswith(".txt"):
            clave = archivo.replace(".txt", "")
            with open(os.path.join(ruta_carpeta, archivo), "r", encoding="utf-8") as f:
                prompts[clave] = {"prompt": f.read().strip()}
    return prompts

def es_indice(texto: str) -> bool:
    # Heurística simple: muchas líneas con formato numerado y pocas frases completas
    lineas = texto.splitlines()
    num_lineas = len(lineas)
    num_items = sum(1 for l in lineas if any(c in l for c in ["1.", "2.", "3.", "I.", "II.", "10.1", "10.2"]))
    num_puntos = texto.count(".")
    return num_items > 5 and num_puntos < (num_lineas * 0.5)

def dividir_contenido(texto: str, max_longitud: int = 10000) -> list:
    fragmentos = []
    inicio = 0
    while inicio < len(texto):
        fin = inicio + max_longitud

        # Intentar cortar en un salto de línea
        if fin < len(texto):
            salto = texto.rfind("\n", inicio, fin)
            if salto != -1 and salto > inicio:
                fin = salto

        fragmentos.append(texto[inicio:fin].strip())
        inicio = fin
    return fragmentos

def leer_contenido_pdf(rutas_pdf: list[str]) -> str:
    contenido = ""
    for ruta in rutas_pdf:
        try:
            with fitz.open(ruta) as doc:
                for page in doc:
                    contenido += page.get_text()
        except Exception as e:
            print(f"⚠️ No se pudo leer el PDF: {ruta} — {e}")
    return contenido.strip()

def openAIRequest(licitacion, tipo_prompt, prompts) -> str:

    # Coge el archivo necesario para lo que quiere hacer
    if tipo_prompt == "requisitos_tecnicos":
        contenido = leer_contenido_pdf([licitacion.GetPDFTecnico()])
    elif tipo_prompt == "requisitos_administrativos":
        contenido = leer_contenido_pdf([licitacion.GetPDFAdministrativo()])
    elif tipo_prompt == "evaluar_adecuacion":
        contenido = licitacion.GetTitulo()
    elif tipo_prompt == "sintesis_requisitos":
        ruta_admin = licitacion.GetResumenAdministrativo()
        ruta_tec = licitacion.GetResumenTecnico()
        if not (ruta_admin and ruta_tec and os.path.exists(ruta_admin) and os.path.exists(ruta_tec)):
            return "❌ No se encontraron los resúmenes previos necesarios para la síntesis."
        try:
            with open(ruta_admin, "r", encoding="utf-8") as f_admin, open(ruta_tec, "r", encoding="utf-8") as f_tec:
                contenido_admin = f_admin.read().strip()
                contenido_tec = f_tec.read().strip()
                contenido = f"--- ADMINISTRATIVO ---\n{contenido_admin}\n\n--- TECNICO ---\n{contenido_tec}"
        except Exception as e:
            return f"❌ Error al leer los archivos de resumen: {e}"
    else:
        raise ValueError("Tipo de prompt no válido")

    if not contenido:
        return "❌ No se pudo extraer texto útil de los PDFs."

    fragmentos = dividir_contenido(contenido, max_longitud=15000)

    subresultados = []
    print(f"📄 Fragmentando documento en {len(fragmentos)} partes...")

    MAX_RETRIES = 3
    WAIT_SECONDS = 5

    if len(fragmentos) > 1:
        prompt_fragmento = prompts.get(f"{tipo_prompt}_fragmento", {}).get("prompt", "")
        for i, fragmento in enumerate(fragmentos):
            if not prompt_fragmento:
                print("⚠️ Prompt para fragmentos no encontrado.")
                return "❌ Falta el prompt para análisis por fragmento."

            prompt = (
                prompt_fragmento
                .replace("{n}", f"{i + 1}/{len(fragmentos)}")
                .replace("{contenido}", fragmento)
            )
            print(f"🔹 Enviando fragmento {i + 1}/{len(fragmentos)}...")


            for intento in range(MAX_RETRIES):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=1500
                    )
                    subresultados.append(response.choices[0].message.content.strip())
                    break
                except Exception as e:
                    print(f"⚠️ Error en intento {intento + 1}/{MAX_RETRIES}: {e}")
                    if intento < MAX_RETRIES - 1:
                        wait = WAIT_SECONDS * (2 ** intento)
                        print(f"⏳ Reintentando en {wait} segundos...")
                        time.sleep(wait)
                    else:
                        print(f"❌ Error crítico en fragmento {i + 1}: {e}")
                        return f"❌ Error al procesar fragmento {i + 1}: {e}"

        print("🧠 Generando análisis final estructurado...")
        resumen_total = "\n\n---\n\n".join(subresultados)
        MAX_PROMPT_CHARS = 20000

        if len(resumen_total) <= MAX_PROMPT_CHARS:
            print("✅ Juntando directamente todos los subresultados en una sola síntesis final.")
            final_prompt = prompts[tipo_prompt]["prompt"].replace("{contenido}", resumen_total)
        else:
            print("🔁 Fragmento total demasiado largo. Aplicando síntesis en bloques intermedios...")
            grupos = [subresultados[:len(subresultados) // 2], subresultados[len(subresultados) // 2:]]
            resumenes_intermedios = []

            for i, grupo in enumerate(grupos):
                print(f"🔄 Sintetizando grupo {i + 1}/{len(grupos)}...")
                grupo_texto = "\n\n---\n\n".join(grupo)

                prompt_union = prompts.get(f"{tipo_prompt}_union", {}).get("prompt", "")
                if not prompt_union:
                    return f"❌ Falta el prompt de síntesis para {tipo_prompt}_union"

                prompt_completo = prompt_union.replace("{contenido}", grupo_texto)

                for intento in range(MAX_RETRIES):
                    try:
                        response = client.chat.completions.create(
                            model="gpt-4",
                            messages=[{"role": "user", "content": prompt_completo}],
                            temperature=0.3,
                            max_tokens=2000
                        )
                        resumenes_intermedios.append(response.choices[0].message.content.strip())
                        break
                    except Exception as e:
                        print(f"⚠️ Error en intento {intento + 1}/{MAX_RETRIES} (grupo {i + 1}): {e}")
                        if intento < MAX_RETRIES - 1:
                            wait = WAIT_SECONDS * (2 ** intento)
                            print(f"⏳ Reintentando en {wait} segundos...")
                            time.sleep(wait)
                        else:
                            return f"❌ Error en síntesis del grupo {i + 1}: {e}"

            resumen_final_input = "\n\n---\n\n".join(resumenes_intermedios)
            prompt_union = prompts.get(f"{tipo_prompt}_union", {}).get("prompt", "")
            final_prompt = prompt_union.replace("{contenido}", resumen_final_input)
    else:
        final_prompt = prompts[tipo_prompt]["prompt"].replace("{contenido}", contenido)

    if tipo_prompt == "requisitos_administrativos":
        final_prompt = final_prompt.replace("{fecha}", licitacion.GetFecha_limite())

    for intento in range(MAX_RETRIES):
        try:
            final_response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": final_prompt}],
                temperature=0.3,
                max_tokens=3000
            )
            return final_response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ Error en intento final {intento + 1}/3: {e}")
            if intento < 2:
                wait = 5 * (2 ** intento)
                print(f"⏳ Reintentando en {wait} segundos...")
                time.sleep(wait)
            else:
                return f"❌ Error durante la síntesis final: {e}"


def extraer_titulos_filtrados(texto):
    lineas = texto.splitlines()
    titulos = []

    for linea in lineas:
        linea = linea.strip()
        if linea.startswith("-"):
            titulos.append(linea[1:].strip())
        elif linea:  # si no empieza con "-", asumimos que es texto plano
            titulos.append(linea)
    return titulos

def filtrar_por_tematicas(lista_licitaciones, prompts):
    prompt_base = prompts.get("filtro_tematicas", {}).get("prompt", "")
    if not prompt_base:
        print("❌ No se encontró el prompt de filtro_tematicas.")
        return lista_licitaciones

    # Armar la lista de títulos en texto
    titulos = [lic.GetTitulo() for lic in lista_licitaciones]
    contenido = "\n".join(f"- {t}" for t in titulos)
    prompt = prompt_base.replace("{contenido}", contenido)

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500
        )
        texto_respuesta = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Error al filtrar por temática: {e}")
        return lista_licitaciones

    # Extraer títulos devueltos por la IA
    titulos_filtrados = extraer_titulos_filtrados(texto_respuesta)
    for lic in lista_licitaciones:
        if lic.GetTitulo().strip() not in titulos_filtrados:
            print(f"❌ DESCARTADA por temática: {lic.GetTitulo()}")

    # Filtrar licitaciones cuyo título esté en la respuesta
    return [lic for lic in lista_licitaciones if lic.GetTitulo().strip() in titulos_filtrados]