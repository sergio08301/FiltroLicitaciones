class Licitacion:
    def __init__(self, empleador, titulo, enlace, fecha_publicacion, fecha_limite, presupuesto, administratives, tecniques):
        self._empleador = empleador.strip()
        self._titulo = titulo.strip()
        self._enlace = enlace.strip()
        self._fecha_publicacion = fecha_publicacion.strip()
        self._fecha_limite = fecha_limite.strip()
        self._presupuesto = presupuesto.strip()
        self._administratives= administratives.strip()
        self._tecniques=tecniques.strip();

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

    def GetAdministratives(self):
        return self._administratives

    def GetTecniques(self):
        return self._tecniques

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

    def setAdministratives(self, nuevo_administratives):
        self._administratives = nuevo_administratives

    def setTecniques(self, nuevo_tecniques):
        self._tecniques = nuevo_tecniques

    def to_print(self):
        return f"""
        Empleador: {self._empleador}
        LICITACIÓN: {self._titulo}
        Enlace: {self._enlace}
        Publicada el: {self._fecha_publicacion}
        Fecha límite: {self._fecha_limite}
        Presupuesto: {self._presupuesto}
        Administratives: {self._administratives}
        Tecniques: {self._tecniques}
        
        """