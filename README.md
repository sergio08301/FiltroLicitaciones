
# 📝 Herramienta de filtrado y procesamiento de licitaciones públicas

## 📦 ¿Qué es esto?
Esta herramienta permite gestionar licitaciones públicas descargando la documentación asociada (plecs administrativos y técnicos) y generando resúmenes y propuestas automáticamente.

Fue diseñada para simplificar y acelerar la preparación de ofertas.

---

## ¿Cómo usarlo?
1. Descomprime el archivo comprimido que te han enviado
   - Dentro encontrarás:
     ```
     FiltroLicitaciones/
     ├── main.exe          ← Haz doble clic aquí
     ├── .env              ← Configuración editable
     └── prompts/          ← Textos editables para IA
     ```
	Es necesario almenos estos tres elementos para la correcta ejecución     

2. Configura el archivo `.env`
   - Abre `.env` con un editor de texto (por ejemplo, Bloc de notas)
   - Completa los campos que veas necesarios. Este programa busca en tu correo electrónico el newsletter de "plataforma.contractacio@gencat.cat"
	En EMAIL_USER hay que escribir tu correo electrónico.
	En EMAIL_PASS no hay que escribir tu contraseña del correo, sino una generada especialmente para esto desde tu cuenta de Google
		Se puede obtener desde este link: https://myaccount.google.com/apppasswords 
		En caso de obtener “La opción de configuración que buscas no está disponible para tu cuenta.” Significa que la cuenta requiere tener activa la verificación en dos pasos, esto se puede activar desde la configuración de la cuenta: https://myaccount.google.com/security 
    - El resto de campos se pueden dejar predeterminados, junto a cada uno hay un comentario que explica brevemente que es lo que hace.
   - Guardar y cerrar el archivo.

3. Personaliza los textos en `prompts/` (opcional)**
   -Se han hecho pruebas con cada documento, pero se ha decidido dejar de forma modificable por si se requiere de algún campo especifico en cada uno de ellos.
   -El proceso de seleccionar que temáticas deben tener las licitaciones está en "filtro_tematicas.txt", los demás son para cado uno de los documentos que el nombre indica.
     Los que acaban en fragmento y unión están preparados para analizar PDFs muy largos pero participan igualmente en crear resúmenes administrativos y técnicos.
   - Puedes editar los archivos `.txt` para adaptar el estilo de los resúmenes y propuestas.

4. Ejecuta el programa haciendo doble clic en `main.exe`
   - Se abrirá el programa.
   - Sigue las instrucciones en pantalla escribiendo números correspondientes a las opciones a elegir
    -En la primera elección usando "1" se crea o modifica con un archivo que almacena las licitaciones (llamado licitaciones.csv)
	                    usando "2" se va escoger que documentos necesitas de las contenidas en el archivo

5. Revisar la información generada
  -Se ha generado un archivo licitaciones.csv que guarda la información de cada licitación junto con como ha de encontrarla el programa, es para uso del propio programa
  -Se genera una carpeta llamada "documentacion", ahí va cada licitación y dentro de ella cada documento generado por el usuario dentro de la licitación correspondiente

---

## Fallos conocidos
- Al descargar los pdfs administrativo y técnico de una licitación se genera un print externo, se está trabajando en hacerlo desaparecer de cara a siguientes versiones.
- En caso de modificación de la pagina contractaciopublica.cat o del newsletter, el programa puede dejar de funcionar
- En caso de mantenimiento de la pagina contractaciopublica.cat esperar a que acabe el mantenimiento

---

## ⚠️ Advertencia
- Acuérdate de revisar los documentos generados en la carpeta de documentacion, 
- Recuerda que estos documentos están generados automáticamente, así que pueden requerir revisión humana antes de usarlos para trámites importantes.

---