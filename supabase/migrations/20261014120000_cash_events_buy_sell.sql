-- Ataraxia — Migracion: cash_events acepta buy/sell, y el brain puede escribirla.
--
-- Contexto (decision de LP, 2026-10-14): cash_events se diseno originalmente solo para
-- movimientos de cash que NO son trades (deposito inicial, dividendos, fees) — el comentario
-- original de la tabla dice "Cash actual = sum(cash_events.amount) - compras + ventas
-- (derivado, no almacenado)", con compras/ventas viviendo en executed_trades, que solo el
-- executor podia escribir (grant select, insert on executed_trades to ataraxia_executor).
--
-- Esa separacion tenia sentido en la arquitectura de fondo simulado. En la arquitectura
-- actual (portafolio real en Schwab, snapshots en Supabase) no hay executor corriendo
-- executed_trades, y LP quiere que cash_events sea el unico historial de movimientos de
-- cash: depositos, retiros, Y las compras/ventas que LP ya ejecuto en Schwab y me cuenta
-- despues. Es logging post-hecho de algo que ya paso en el broker — nunca una orden que el
-- brain inicia. El limite real (brain nunca tiene acceso de ejecucion sobre el broker) sigue
-- intacto: esto es anotar un hecho, no accionar una orden.
--
-- Convencion de signo para buy/sell (mismo criterio que depositos/retiros):
--   buy  -> amount NEGATIVO (el cash sale de la cuenta hacia la compra)
--   sell -> amount POSITIVO (el cash entra a la cuenta desde la venta)
-- No se agregan columnas de ticker/cantidad/precio: ese detalle granular ya vive en
-- portfolio_lots entre snapshots consecutivos. Esta tabla es el libro de caja, no el
-- blotter de trades — poner "UNH 1.0183 @ $398.49" en 'note' basta para que el humano
-- entienda el evento sin duplicar una fuente de verdad que ya existe en otro lado.
--
-- Aplicar desde el SQL Editor de Supabase con credenciales de admin — ataraxia_brain no
-- puede hacer DDL ni GRANT, por diseño.

alter table cash_events drop constraint if exists cash_events_event_type_check;
alter table cash_events add constraint cash_events_event_type_check
    check (event_type in ('deposit', 'withdrawal', 'dividend', 'fee', 'interest', 'buy', 'sell'));

grant insert on cash_events to ataraxia_brain;
