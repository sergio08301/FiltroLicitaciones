from dotenv import load_dotenv
import os

load_dotenv()

print("Usuario:", os.getenv("EMAIL_USER"))
print("Contraseña:", os.getenv("EMAIL_PASS"))