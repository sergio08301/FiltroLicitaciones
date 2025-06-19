import os
from openai import OpenAI
import fitz  # PyMuPDF
import os
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


    #Coge el archivo necesario para lo que quiere hacer
    if tipo_prompt == "requisitos_tecnicos":    #Resumen del PDF tecnico
        contenido = leer_contenido_pdf([licitacion.GetTecniques()])
    elif tipo_prompt == "requisitos_administrativos":   #Resumen del PDF administrativo
        contenido = leer_contenido_pdf([licitacion.GetAdministratives()])
    elif tipo_prompt == "evaluar_adecuacion":
        contenido = licitacion.GetTitulo()
    elif tipo_prompt == "sintesis_requisitos": #TODO hay que crear y poder asignar estos docuemntos a la licitación aun
        contenido = leer_contenido_pdf([licitacion.GetResumenAdministrativo()])+"\n\n---\n\n".join(leer_contenido_pdf([licitacion.GetResumenTecnico()]))
    else:
        raise ValueError("Tipo de prompt no válido")

    if not contenido:
        return "❌ No se pudo extraer texto útil de los PDFs."

    # Fragmentar el contenido en partes de hasta 10,000 caracteres (~3000 tokens)
    fragmentos = dividir_contenido(contenido, max_longitud=10000)
    subresultados = []
    print(f"📄 Fragmentando documento en {len(fragmentos)} partes...")

    #Si no cabe en una misma request hay que dividirlo en fragmentos
    if len(fragmentos)>1:
        # Prompt para fragmentos
        prompt_fragmento = prompts.get(f"{tipo_prompt}_fragmento", {}).get("prompt", "")

        for i, fragmento in enumerate(fragmentos):
            if not prompt_fragmento:
                print("⚠️ Prompt para fragmentos no encontrado.")
                return "❌ Falta el prompt para análisis por fragmento."

            prompt = prompt_fragmento.replace("{n}", f"{i + 1}/{len(fragmentos)}") + "\n\n" + fragmento
            print(f"🔹 Enviando fragmento {i + 1}/{len(fragmentos)}...")

            try:
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1500
                )
                subresultados.append(response.choices[0].message.content.strip())
            except Exception as e:
                subresultados.append(f"❌ Error en fragmento {i + 1}: {e}")


        print("🧠 Generando análisis final estructurado...")

        # Juntar todos los subresultados y ver si caben en una sola síntesis
        resumen_total = "\n\n---\n\n".join(subresultados)
        MAX_PROMPT_CHARS = 20000  # ~6-7k tokens

        if len(resumen_total) <= MAX_PROMPT_CHARS:
            print("✅ Juntando directamente todos los subresultados en una sola síntesis final.")
            final_prompt = prompts[tipo_prompt]["prompt"].replace("{contenido}", resumen_total)
        else:
            print("🔁 Fragmento total demasiado largo. Aplicando síntesis en bloques intermedios...")

            # Agrupar en dos bloques
            grupos = [subresultados[:len(subresultados) // 2], subresultados[len(subresultados) // 2:]]
            resumenes_intermedios = []

            for i, grupo in enumerate(grupos):
                print(f"🔄 Sintetizando grupo {i + 1}/{len(grupos)}...")
                grupo_texto = "\n\n---\n\n".join(grupo)

                prompt_union = prompts.get(f"{tipo_prompt}_union", {}).get("prompt", "")
                if not prompt_union:
                    return f"❌ Falta el prompt de síntesis para {tipo_prompt}_union"

                prompt_completo = prompt_union.replace("{contenido}", grupo_texto)

                try:
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": prompt_completo}],
                        temperature=0.3,
                        max_tokens=1500
                    )
                    resumenes_intermedios.append(response.choices[0].message.content.strip())
                except Exception as e:
                    return f"❌ Error en síntesis del grupo {i + 1}: {e}"

            # Síntesis final de los resúmenes intermedios
            resumen_final_input = "\n\n---\n\n".join(resumenes_intermedios)
            prompt_union = prompts.get(f"{tipo_prompt}_union", {}).get("prompt", "")
            final_prompt = prompt_union.replace("{contenido}", resumen_final_input)

    else:
        final_prompt = prompts[tipo_prompt]["prompt"].replace("{contenido}", contenido)



    # Enviar a OpenAI
    try:
        final_response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": final_prompt}],
            temperature=0.3,
            max_tokens=1500
        )
        return final_response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Error durante la síntesis final: {e}"