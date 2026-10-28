USE TraficoIA;
GO
-- La API y Power BI ya NO consultan la tabla directamente.
-- Todo pasa por los procedimientos almacenados de 03_procedimientos.sql.
-- Ejemplos para probar en SSMS (los mismos que ejecuta la API):

-- 1. Historico de todas las clasificaciones (tabla fuente del dashboard)
EXEC dbo.sp_Dashboard_Registros;
GO
-- 2. Con filtros (NULL o parametro omitido = sin filtro)
EXEC dbo.sp_Dashboard_Registros @FechaDesde = '2026-10-01', @FechaHasta = '2026-10-28',
     @Protocolo = 'TCP', @Puerto = 443;
GO
-- 3. KPIs
EXEC dbo.sp_Dashboard_Resumen @Clasificacion = 'Sospechoso';
GO
-- 4. Puertos con mas alertas
EXEC dbo.sp_Dashboard_PorPuerto @Clasificacion = 'Sospechoso', @Top = 10;
GO
