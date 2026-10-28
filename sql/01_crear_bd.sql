-- Ejecutar en SSMS con permisos CREATE DATABASE.
IF DB_ID(N'TraficoIA') IS NULL CREATE DATABASE TraficoIA;
GO
USE TraficoIA;
GO
IF OBJECT_ID(N'dbo.PrediccionesTrafico', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.PrediccionesTrafico (
    id_prediccion BIGINT IDENTITY(1,1) PRIMARY KEY,
    fecha_prediccion DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    duracion FLOAT NOT NULL,
    paquetes BIGINT NOT NULL,
    bytes BIGINT NOT NULL,
    puerto INT NOT NULL,
    protocolo VARCHAR(10) NOT NULL,
    intentos_fallidos INT NOT NULL,
    probabilidad FLOAT NOT NULL,
    clasificacion VARCHAR(15) NOT NULL,
    CONSTRAINT CK_Trafico_Clas CHECK (clasificacion IN ('Normal','Sospechoso')),
    CONSTRAINT CK_Trafico_Prob CHECK (probabilidad BETWEEN 0 AND 1)
  );
  CREATE INDEX IX_Predicciones_Fecha ON dbo.PrediccionesTrafico(fecha_prediccion);
END;
GO
