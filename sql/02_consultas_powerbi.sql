USE TraficoIA;
GO
-- 1. Histórico de todas las clasificaciones (Power BI puede conectarse a tabla directamente).
SELECT id_prediccion, fecha_prediccion, puerto, protocolo,
       intentos_fallidos, probabilidad, clasificacion
FROM dbo.PrediccionesTrafico;
GO
-- 2. Resumen por fecha y resultado
SELECT CAST(fecha_prediccion AS date) AS fecha,
       clasificacion, COUNT(*) AS total
FROM dbo.PrediccionesTrafico
GROUP BY CAST(fecha_prediccion AS date), clasificacion
ORDER BY fecha;
GO
-- 3. Puertos con más alertas
SELECT TOP (10) puerto, COUNT(*) AS total_sospechosas
FROM dbo.PrediccionesTrafico
WHERE clasificacion = 'Sospechoso'
GROUP BY puerto
ORDER BY total_sospechosas DESC;
GO
