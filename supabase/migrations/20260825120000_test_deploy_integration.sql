-- Ataraxia — migracion de prueba, sin efecto en schema/datos.
--
-- Unico proposito: validar que la integracion de GitHub de Supabase ("Deploy to
-- production") efectivamente aplica migraciones nuevas al hacer push/merge a main.
-- Se detecto que estaba apagada y por eso las migraciones 2 y 3 nunca se auto-desplegaron
-- (se corrieron a mano en el SQL Editor el 2026-08-25). Este archivo confirma que, con el
-- toggle ya activado, el flujo automatico vuelve a funcionar.
--
-- Verificacion: select obj_description('public.decisions'::regclass); deberia devolver el
-- texto del comment de abajo despues del deploy.

comment on table public.decisions is 'Ataraxia: registro append-only de propuestas y revisiones del brain.';
