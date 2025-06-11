class Licitacion:
    def __init__(self, empleador, titulo, enlace, fecha_publicacion, fecha_limite, presupuesto):
        self._empleador = empleador.strip()
        self._titulo = titulo.strip()
        self._enlace = enlace.strip()
        self._fecha_publicacion = fecha_publicacion.strip()
        self._fecha_limite = fecha_limite.strip()
        self._presupuesto = presupuesto.strip()

# Getters
def GetEmpleador(self):
    return self._empleador

def GetTitulo(self):
    return self._titulo

def GetEnlace(self):
    return self._enlace

def GetFecha_publicacion(self):
    return self._fecha_publicacion

def GetFecha_limite(self):
    return self._fecha_limite

def GetPresupuesto(self):
    return self._presupuesto

# Setters
def SetEmpleador(self, nuevo_empleador):
    self._empleador = nuevo_empleador

def SetTitulo(self, nuevo_titulo):
    self._titulo = nuevo_titulo

def SetEnlace(self, nuevo_enlace):
    self._enlace = nuevo_enlace

def setFecha_publicacion(self, nueva_fecha):
    self._fecha_publicacion = nueva_fecha

def setFecha_limite(self, nueva_fecha):
    self._fecha_limite = nueva_fecha

def setPresupuesto(self, nuevo_presupuesto):
    self._presupuesto = nuevo_presupuesto

def to_print(self):
    return f"""
    LICITACIÓN: {self._titulo}
    Enlace: {self._enlace}
    Publicada el: {self._fecha_publicacion}
    Fecha límite: {self._fecha_limite}
    Presupuesto: {self._presupuesto}
    """