-- Ataraxia — segunda migracion de prueba, sin efecto en schema/datos.
--
-- La primera prueba (20260825120000_test_deploy_integration.sql) no se auto-desplego porque
-- el toggle "Deploy to production" no habia quedado guardado. Este archivo reintenta la
-- misma validacion despues de confirmar que el toggle esta encendido y guardado.
--
-- Verificacion: select obj_description('public.positions'::regclass); deberia devolver el
-- texto del comment de abajo despues del deploy.

comment on table public.positions is 'Ataraxia: snapshot diario derivado de executed_trades, usado por el brain para su PortfolioState.';
