import csv

class Licitacion:
    def __init__(self, empleador, titulo, enlace, fecha_publicacion, fecha_limite, presupuesto):
        self._empleador = empleador.strip()
        self._titulo = titulo.strip()
        self._enlace = enlace.strip()
        self._fecha_publicacion = fecha_publicacion.strip()
        self._fecha_limite = fecha_limite.strip()
        self._presupuesto = presupuesto.strip()
        #Docuemntos a añadir posteriormente a la creación
        self._PDFAdministrativo = ""
        self._PDFTecnico = ""
        self._ResumenAdministrativo = ""
        self._ResumenTecnico = ""
        self._SintesisRequisitos = ""
        self._IntroduccionOferta = ""
        self._MemoriaTecnica = ""
        self._CriteriosSocialesMedioambientales = ""
        self._PropuestaEconomica = ""
        self._DocumentacionAdministrativaSolvencia = ""

    # Getters
    def GetEmpleador(self): return self._empleador

    def GetTitulo(self): return self._titulo

    def GetEnlace(self): return self._enlace

    def GetFecha_publicacion(self): return self._fecha_publicacion

    def GetFecha_limite(self): return self._fecha_limite

    def GetPresupuesto(self): return self._presupuesto

    def GetPDFAdministrativo(self): return self._PDFAdministrativo

    def GetPDFTecnico(self): return self._PDFTecnico

    def GetResumenAdministrativo(self): return self._ResumenAdministrativo

    def GetResumenTecnico(self): return self._ResumenTecnico

    def GetSintesisRequisitos(self): return self._SintesisRequisitos

    def GetIntroduccionOferta(self): return self._IntroduccionOferta

    def GetMemoriaTecnica(self): return self._MemoriaTecnica

    def GetCriteriosSocialesMedioambientales(self): return self._CriteriosSocialesMedioambientales

    def GetPropuestaEconomica(self): return self._PropuestaEconomica

    def GetDocumentacionAdministrativaSolvencia(self): return self._DocumentacionAdministrativaSolvencia

    # Setters
    def SetEmpleador(self, v): self._empleador = v

    def SetTitulo(self, v): self._titulo = v

    def SetEnlace(self, v): self._enlace = v

    def SetFecha_publicacion(self, v): self._fecha_publicacion = v

    def SetFecha_limite(self, v): self._fecha_limite = v

    def SetPresupuesto(self, v): self._presupuesto = v

    def SetPDFAdministrativo(self, v): self._PDFAdministrativo = v

    def SetPDFTecnico(self, v): self._PDFTecnico = v

    def SetResumenAdministrativo(self, v): self._ResumenAdministrativo = v

    def SetResumenTecnico(self, v): self._ResumenTecnico = v

    def SetSintesisRequisitos(self, v): self._SintesisRequisitos = v

    def SetIntroduccionOferta(self, v): self._IntroduccionOferta = v

    def SetMemoriaTecnica(self, v): self._MemoriaTecnica = v

    def SetCriteriosSocialesMedioambientales(self, v): self._CriteriosSocialesMedioambientales = v

    def SetPropuestaEconomica(self, v): self._PropuestaEconomica = v

    def SetDocumentacionAdministrativaSolvencia(self, v): self._DocumentacionAdministrativaSolvencia = v


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
        Introducción Oferta: {self._IntroduccionOferta}
        Memoria Técnica: {self._MemoriaTecnica}
        Criterios Sociales y Medioambientales: {self._CriteriosSocialesMedioambientales}
        Propuesta Económica: {self._PropuestaEconomica}
        Documentación Administrativa y Solvencia: {self._DocumentacionAdministrativaSolvencia}
        """