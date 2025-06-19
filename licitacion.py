import csv

class Licitacion:
    def __init__(self, empleador, titulo, enlace, fecha_publicacion, fecha_limite, presupuesto, administratives, tecniques):
        self._empleador = empleador.strip()
        self._titulo = titulo.strip()
        self._enlace = enlace.strip()
        self._fecha_publicacion = fecha_publicacion.strip()
        self._fecha_limite = fecha_limite.strip()
        self._presupuesto = presupuesto.strip()
        self._administratives = administratives.strip() if administratives else ""
        self._tecniques = tecniques.strip() if tecniques else ""
        self._resumen_administrativo = ""
        self._resumen_tecnico = ""
        self._sintesis = ""

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

    def GetResumenAdministrativo(self):
        return self._resumen_administrativo

    def GetResumenTecnico(self):
        return self._resumen_tecnico

    def GetSintesis(self):
        return self._sintesis

    # Setters
    def SetEmpleador(self, nuevo_empleador):
        self._empleador = nuevo_empleador

    def SetTitulo(self, nuevo_titulo):
        self._titulo = nuevo_titulo

    def SetEnlace(self, nuevo_enlace):
        self._enlace = nuevo_enlace

    def SetFecha_publicacion(self, nueva_fecha):
        self._fecha_publicacion = nueva_fecha

    def SetFecha_limite(self, nueva_fecha):
        self._fecha_limite = nueva_fecha

    def SetPresupuesto(self, nuevo_presupuesto):
        self._presupuesto = nuevo_presupuesto

    def SetAdministratives(self, nuevo_administratives):
        self._administratives = nuevo_administratives

    def SetTecniques(self, nuevo_tecniques):
        self._tecniques = nuevo_tecniques

    def SetResumenTecnico(self, path):
        self._resumen_tecnico = path

    def SetResumenAdministrativo(self, path):
        self._resumen_administrativo = path

    def SetSintesis(self, path):
        self._sintesis = path


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
