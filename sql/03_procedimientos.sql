-- Procedimientos almacenados usados por la API (api.py).
-- La API NO ejecuta SQL directo sobre la tabla: solo llama a estos SP.
-- Ejecutar en SSMS despues de 01_crear_bd.sql.
--
-- Filtros comunes de los SP del dashboard (todos opcionales, NULL = sin filtro):
--   @FechaDesde, @FechaHasta (DATE, UTC; @FechaHasta incluye el dia completo),
--   @Protocolo, @Puerto, @Clasificacion.
-- OPTION (RECOMPILE) permite que SQL Server use IX_Predicciones_Fecha
-- cuando llega un filtro de fecha y lo ignore cuando viene NULL.
USE TraficoIA;
GO

-- =========================================
-- Insercion (la usa POST /api/trafico/predecir y /lote)
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_InsertarPrediccion
  @Duracion FLOAT,
  @Paquetes BIGINT,
  @Bytes BIGINT,
  @Puerto INT,
  @Protocolo VARCHAR(10),
  @IntentosFallidos INT,
  @Probabilidad FLOAT,
  @Clasificacion VARCHAR(15)
AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO dbo.PrediccionesTrafico
    (duracion, paquetes, bytes, puerto, protocolo, intentos_fallidos, probabilidad, clasificacion)
  VALUES
    (@Duracion, @Paquetes, @Bytes, @Puerto, @Protocolo, @IntentosFallidos, @Probabilidad, @Clasificacion);
END;
GO

-- =========================================
-- Validacion comun de los filtros
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_ValidarFiltros
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Puerto INT = NULL
AS
BEGIN
  SET NOCOUNT ON;
  IF @FechaDesde IS NOT NULL AND @FechaHasta IS NOT NULL AND @FechaDesde > @FechaHasta
    THROW 50001, 'FechaDesde no puede ser posterior a FechaHasta', 1;
  IF @Puerto IS NOT NULL AND (@Puerto < 0 OR @Puerto > 65535)
    THROW 50002, 'Puerto fuera de rango (0-65535)', 1;
END;
GO

-- =========================================
-- 1. Detalle: tabla fuente del dashboard
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_Registros
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL,
  @Limite INT = NULL
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;
  IF @Limite IS NOT NULL AND @Limite < 1
    THROW 50003, 'Limite debe ser un entero positivo', 1;

  SELECT TOP (ISNULL(@Limite, 2147483647))
         id_prediccion, fecha_prediccion, duracion, paquetes, bytes,
         puerto, protocolo, intentos_fallidos, probabilidad, clasificacion
  FROM dbo.PrediccionesTrafico
  WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
    AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
    AND (@Protocolo IS NULL OR protocolo = @Protocolo)
    AND (@Puerto IS NULL OR puerto = @Puerto)
    AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)
  ORDER BY fecha_prediccion DESC, id_prediccion DESC
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- 2. KPIs generales (una fila)
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_Resumen
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;

  SELECT COUNT(*) AS total_conexiones,
         SUM(CASE WHEN clasificacion <> 'Normal' THEN 1 ELSE 0 END) AS total_sospechosas,
         AVG(CAST(probabilidad AS FLOAT)) AS probabilidad_promedio,
         AVG(CAST(duracion AS FLOAT)) AS duracion_promedio,
         AVG(CAST(paquetes AS FLOAT)) AS paquetes_promedio,
         SUM(CAST(bytes AS BIGINT)) AS bytes_totales,
         SUM(intentos_fallidos) AS intentos_fallidos_totales
  FROM dbo.PrediccionesTrafico
  WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
    AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
    AND (@Protocolo IS NULL OR protocolo = @Protocolo)
    AND (@Puerto IS NULL OR puerto = @Puerto)
    AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- 3. Conteo por clasificacion
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_PorClasificacion
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;

  SELECT clasificacion, COUNT(*) AS total,
         AVG(CAST(probabilidad AS FLOAT)) AS probabilidad_promedio
  FROM dbo.PrediccionesTrafico
  WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
    AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
    AND (@Protocolo IS NULL OR protocolo = @Protocolo)
    AND (@Puerto IS NULL OR puerto = @Puerto)
    AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)
  GROUP BY clasificacion
  ORDER BY total DESC
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- 4. Protocolo x clasificacion
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_PorProtocolo
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;

  SELECT protocolo, clasificacion, COUNT(*) AS total,
         AVG(CAST(bytes AS FLOAT)) AS bytes_promedio
  FROM dbo.PrediccionesTrafico
  WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
    AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
    AND (@Protocolo IS NULL OR protocolo = @Protocolo)
    AND (@Puerto IS NULL OR puerto = @Puerto)
    AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)
  GROUP BY protocolo, clasificacion
  ORDER BY protocolo, total DESC
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- 5. Puerto x clasificacion (@Top combinaciones con mas registros)
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_PorPuerto
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL,
  @Top INT = 10
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;
  -- Mismo rango que antes: 1 a 100
  SET @Top = CASE WHEN @Top IS NULL THEN 10
                  WHEN @Top < 1 THEN 1
                  WHEN @Top > 100 THEN 100
                  ELSE @Top END;

  SELECT TOP (@Top) puerto, clasificacion, COUNT(*) AS total
  FROM dbo.PrediccionesTrafico
  WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
    AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
    AND (@Protocolo IS NULL OR protocolo = @Protocolo)
    AND (@Puerto IS NULL OR puerto = @Puerto)
    AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)
  GROUP BY puerto, clasificacion
  ORDER BY total DESC
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- 6. Distribucion de probabilidad en tramos de 10 %
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_DistribucionProbabilidad
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;

  SELECT rango, clasificacion, COUNT(*) AS total
  FROM (SELECT clasificacion,
               CASE WHEN probabilidad >= 1 THEN 9
                    ELSE FLOOR(probabilidad * 10) END AS bucket,
               CONCAT(CASE WHEN probabilidad >= 1 THEN 90
                           ELSE FLOOR(probabilidad * 10) * 10 END,
                      '-',
                      CASE WHEN probabilidad >= 1 THEN 100
                           ELSE FLOOR(probabilidad * 10) * 10 + 10 END, '%') AS rango
        FROM dbo.PrediccionesTrafico
        WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
          AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
          AND (@Protocolo IS NULL OR protocolo = @Protocolo)
          AND (@Puerto IS NULL OR puerto = @Puerto)
          AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)) t
  GROUP BY bucket, rango, clasificacion
  ORDER BY bucket
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- 7. Intentos fallidos x clasificacion
-- =========================================
CREATE OR ALTER PROCEDURE dbo.sp_Dashboard_IntentosFallidos
  @FechaDesde DATE = NULL,
  @FechaHasta DATE = NULL,
  @Protocolo VARCHAR(10) = NULL,
  @Puerto INT = NULL,
  @Clasificacion VARCHAR(15) = NULL
AS
BEGIN
  SET NOCOUNT ON;
  EXEC dbo.sp_ValidarFiltros @FechaDesde, @FechaHasta, @Puerto;

  SELECT intentos_fallidos, clasificacion, COUNT(*) AS total,
         AVG(CAST(probabilidad AS FLOAT)) AS probabilidad_promedio
  FROM dbo.PrediccionesTrafico
  WHERE (@FechaDesde IS NULL OR fecha_prediccion >= @FechaDesde)
    AND (@FechaHasta IS NULL OR fecha_prediccion < DATEADD(DAY, 1, @FechaHasta))
    AND (@Protocolo IS NULL OR protocolo = @Protocolo)
    AND (@Puerto IS NULL OR puerto = @Puerto)
    AND (@Clasificacion IS NULL OR clasificacion = @Clasificacion)
  GROUP BY intentos_fallidos, clasificacion
  ORDER BY intentos_fallidos
  OPTION (RECOMPILE);
END;
GO

-- =========================================
-- Pruebas rapidas en SSMS
-- =========================================
-- EXEC dbo.sp_Dashboard_Registros;
-- EXEC dbo.sp_Dashboard_Registros @FechaDesde='2026-10-01', @FechaHasta='2026-10-28', @Protocolo='TCP', @Puerto=443;
-- EXEC dbo.sp_Dashboard_Resumen @Clasificacion='Sospechoso';
-- EXEC dbo.sp_Dashboard_PorPuerto @Top=5;
