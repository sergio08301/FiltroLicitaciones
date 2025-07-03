import csv

class Licitacion:
    def __init__(self, empleador, titulo, enlace, fecha_publicacion, fecha_limite, presupuesto, PDFAdministrativo, PDFTecnico):
        self._empleador = empleador.strip()
        self._titulo = titulo.strip()
        self._enlace = enlace.strip()
        self._fecha_publicacion = fecha_publicacion.strip()
        self._fecha_limite = fecha_limite.strip()
        self._presupuesto = presupuesto.strip()
        self._PDFAdministrativo = PDFAdministrativo.strip() if PDFAdministrativo else ""
        self._PDFTecnico = PDFTecnico.strip() if PDFTecnico else ""
        # Tras llamada a la API
        self._ResumenAdministrativo = ""
        self._ResumenTecnico = ""
        self._SintesisRequisitos = ""

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

    def GetPDFAdministrativo(self):
        return self._PDFAdministrativo

    def GetPDFTecnico(self):
        return self._PDFTecnico

    def GetResumenAdministrativo(self):
        return self._ResumenAdministrativo

    def GetResumenTecnico(self):
        return self._ResumenTecnico

    def GetSintesisRequisitos(self):
        return self._SintesisRequisitos

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

    def SetPDFAdministrativo(self, nuevo_path):
        self._PDFAdministrativo = nuevo_path

    def SetPDFTecnico(self, nuevo_path):
        self._PDFTecnico = nuevo_path

    def SetResumenAdministrativo(self, resumen_path):
        self._ResumenAdministrativo = resumen_path

    def SetResumenTecnico(self, resumen_path):
        self._ResumenTecnico = resumen_path

    def SetSintesisRequisitos(self, resumen_path):
        self._SintesisRequisitos = resumen_path


    def to_print(self):
        return f"""
        Empleador: {self._empleador}
        LICITACIÓN: {self._titulo}
        Enlace: {self._enlace}
        Publicada el: {self._fecha_publicacion}
        Fecha límite: {self._fecha_limite}
        Presupuesto: {self._presupuesto}
        PDF Administrativo: {self._PDFAdministrativo}
        PDF Técnico: {self._PDFTecnico}
        Resumen Administrativo: {self._ResumenAdministrativo}
        Resumen Técnico: {self._ResumenTecnico}
        Síntesis Requisitos: {self._SintesisRequisitos}
        """
