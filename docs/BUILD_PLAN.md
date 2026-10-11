# Ataraxia — Plan de Desarrollo Técnico

*Complementa a `PROJECT_PLAN.md` (estrategia/producto). Este documento es el roadmap de
implementación: fases, stack, estructura de repo, y decisiones de arquitectura.*

*Última actualización: 11 de octubre, 2026*

> **Contexto de arquitectura (desde el 7-oct).** Se descartó el fondo simulado de $1M, se
> descartó IBKR, se descartó la fase de paper trading y se descartó el executor automatizado.
> Ataraxia analiza la **cuenta real de Schwab** del usuario en solo lectura, y el usuario
> ejecuta a mano de forma permanente.
>
> **Decisiones del 11-oct, ya implementadas:** universo sin restricción de índice con piso de
> $2B (1,681 nombres), kill-switch de drawdown activo en −30%, el portafolio versionado en
> Supabase a nivel de lote, el alpha medido **solo sobre equities**, el lote rotativo bajado a
> 8 por semana, y la automation diaria de barrido de noticias creada.
>
> Este documento se desactualizó dos veces en cuatro días. Si una sección dice "pendiente",
> verificá contra el código antes de creerle — y verificá que estás leyendo el repo vivo en
> `~/ataraxia` y no la copia obsoleta en Documents (ver "Riesgos cerrados").

## Misión que gobierna este documento

Ataraxia existe para **vencer al S&P 500 a largo plazo** (ver `PROJECT_PLAN.md` → Misión).
Toda decisión técnica de aquí se juzga por si acerca o aleja de ese fin. En particular: la
métrica de alpha relativo contra `^GSPC` no es un nice-to-have del dashboard, es el
instrumento de medición del propósito del proyecto, y por eso el pipeline de benchmark es
infraestructura crítica, no reporting cosmético.

## Principio de Diseño Central: Guardrails en Código, no en el LLM

Antes de las fases — esto es lo más importante de todo el documento y no debe negociarse
más adelante por conveniencia: **el LLM propone, el código decide.** Los guardrails
(máximo 15% por posición, trigger de -20% para revisión de tesis, sin same-day round-trips,
máximo de posiciones) se implementan como validaciones deterministas en código que corren
*antes* de que cualquier propuesta llegue al usuario como recomendación ejecutable — nunca
como una instrucción en el prompt que confiamos en que el modelo respete. Un LLM puede
razonar mal un día, tener un lapso, o ser manipulado por un prompt injection en una noticia
que lee vía web search. El código de validación no negocia. Si una decisión del agente viola
un guardrail, la propuesta se marca como "rechazada por guardrail" y se loguea — el agente no
tiene autoridad para saltárselo.

**Qué cambió con la ejecución manual permanente:** antes el guardrail era la última línea
antes de una orden automática al broker. Ahora el último filtro es el usuario. Eso *no*
degrada el guardrail a sugerencia: su función sigue siendo que una propuesta inválida nunca
se presente como accionable, para que el usuario no tenga que auditar a mano cada
recomendación. El humano es el ejecutor, no el validador.

## Arquitectura: Brain (OpenClaw) + Ejecución manual (usuario)

**El "brain"** — automatización programada en OpenClaw, corriendo en la máquina del usuario.
Hace todo el trabajo que requiere leer contenido no confiable (research vía web search,
fundamentales, noticias) y razonar sobre la cartera, y **escribe propuestas con rationale +
bear case + probabilidad**. No tiene ninguna ruta a mover dinero: no hay cuenta de broker
conectada con permisos de escritura, en ningún lado del sistema.

**La ejecución** — el usuario, de forma permanente. Lee las propuestas y decide qué ejecuta en
Schwab a mano. Esto ya no es una fase transitoria hacia la automatización: es la arquitectura
objetivo. La pieza que procesa contenido potencialmente hostil es estructuralmente incapaz de
mover dinero real, sin importar qué logre convencerla de hacer.

**Consecuencia asumida y documentada:** medir "Ataraxia + veto humano" en lugar de Ataraxia
sola introduce un sesgo real en la evaluación del alpha — si el usuario filtra propuestas, el
registro ya no atribuye limpiamente el resultado al agente. La versión anterior de este
documento usó exactamente ese argumento para justificar ejecución automatizada. Con la
decisión del 7-oct (capital real desde el día uno, sin cuenta separada), el trade-off se
invierte: la seguridad de no tener un LLM con autoridad sobre dinero real pesa más que la
limpieza estadística de la medición. **Mitigación obligatoria:** cuando el usuario decline o
modifique una propuesta, eso se loguea igual que una ejecución, para poder reconstruir después
qué habría hecho Ataraxia sola vs. qué se hizo realmente. Sin ese registro, la pregunta "¿le
ganó al S&P 500?" no tiene respuesta atribuible, y la misión del proyecto queda sin medir.

**Hosting:** OpenClaw, local. El brain corrió originalmente como tarea programada de Cowork,
pero el sandbox de red de Cowork bloqueaba la conexión a Supabase (ver "Riesgos cerrados").
Costo asumido del cambio: el Gateway de OpenClaw debe estar corriendo a la hora del job; si la
máquina está apagada o dormida, el ciclo de ese día no ocurre.

## Fuente de verdad del portafolio — ✅ **cerrado el 2026-10-11**

Decidido el 7-oct: **la cuenta real de Schwab es el objeto de análisis**, en solo lectura.
Revisado el 11-oct por decisión de LP: **el portafolio se versiona en Supabase**, no como un
CSV que se sobreescribe. Cada corte queda guardado con su fecha, y la serie de snapshots es
lo que después permite medir el retorno contra el S&P 500 sin trabajo adicional.

> **Corrección de registro.** La versión anterior de esta sección (fechada 8-oct) declaraba
> este gap como "no implementado" y "el bloqueador real del proyecto". Era un diagnóstico
> hecho sobre la copia obsoleta del repo en `~/Documents/Claude/Projects/Financial Agent/`.
> El lector del CSV de Schwab (`src/data/portfolio_csv.py`) ya existía desde el 7-oct en el
> repo vivo (`~/ataraxia`). La lección operativa está al final, en "Riesgos cerrados".

Cómo quedó, a nivel de lote:

- [x] **Parser de los "Lot Details" de Schwab** (`src/data/schwab_lots.py`): un archivo por
      ticker, con fecha de apertura, costo y holding period de cada compra. Exige que todos
      los archivos sean del mismo corte — mezclar fechas produciría un portafolio que nunca
      existió. Clasifica equity vs ETF usando el screener de Nasdaq como evidencia positiva
      (los ETFs no aparecen ahí) más una lista explícita de ETFs conocidos.
- [x] **Tabla `portfolio_lots` + vista `portfolio_positions`**
      (migración `20261011180000_portfolio_lots.sql`). Las posiciones se *derivan* de los
      lotes: una sola fuente de verdad, sin riesgo de que agregado y detalle se contradigan.
      Se guarda a nivel de lote porque la fecha de compra no se puede reconstruir desde el
      agregado, y es lo que permite distinguir short/long term y medir cuánto lleva sostenida
      una tesis.
- [x] **Cargador** (`scripts/load_portfolio_snapshot.py`), con `--dry-run`. Inserta snapshot y
      lotes en una sola transacción: un snapshot a medias sería un portafolio que nunca
      existió y el brain lo leería como verdad. Rechaza cargar dos veces la misma fecha.
- [x] **El brain lee de la DB** (`portfolio_csv.load_latest()`, que prefiere Supabase y cae al
      CSV solo si no hay red ni credenciales, con aviso). `brain_portfolio`, `brain_decide`,
      `brain_candidates`, `run_cycle` y `compute_performance` ya apuntan ahí.
- [x] **Aviso de frescura** conservado: `STALE_AFTER_DAYS = 14`, y el prompt del ciclo
      instruye a decirlo en el reporte.
- [x] **Cash incluido** en el estado (al 8-oct: $100.84), que el validator necesita para la
      regla de cash suficiente.
- [x] **Primer snapshot cargado:** id 5, corte 2026-10-08, 79 lotes en 16 posiciones
      (13 equities, 3 ETFs). Costo $8,973.32, valor $10,296.74, cuenta total $10,397.58.
      Reconciliado contra los totales que reporta Schwab, sin discrepancias.

**Bug encontrado y corregido al conectar esto (vale documentarlo porque era silencioso):**
`gain_pct` y `pct_of_account` van en **puntos porcentuales** (12.41), no en fracción (0.1241),
porque es lo que trae el export de Schwab y lo que compara el trigger de revisión de tesis
(`gain_pct <= -20`). La primera versión del lector desde la DB devolvía la fracción, con lo
cual **el trigger de −20% no se habría disparado nunca**: IREN (−29.15%) e INFQ (−30.95%)
pasaban sin flaggearse. Un bug de unidades que no rompe nada visible pero apaga un guardrail.

**Guarda de lectura:** quedó un snapshot de prueba con `as_of 1999-01-01` y
`source_file 'probe.csv'`. `ataraxia_brain` no tiene DELETE por diseño, así que se filtra en
lectura con `PORTFOLIO_EPOCH = date(2026, 1, 1)`, definido en `src/db/models.py` (la capa
baja, para tener una sola definición sin ciclo de imports) y aplicado tanto en
`get_latest_snapshot()` como en `get_snapshot_history()`. No es cosmético: un snapshot de 1999
dentro de una serie de performance produce retornos y drawdowns sin sentido.

- [ ] **Pendiente del usuario:** borrar esa fila (`delete from portfolio_snapshots where
      as_of = '1999-01-01'`) desde el SQL Editor. Mientras no se borre, el filtro la cubre.
- [ ] **Pendiente del usuario:** decidir si en algún momento se conecta la API de Schwab en
      solo lectura para que el snapshot se actualice solo, o si subir los "Lot Details" a mano
      es suficiente de forma permanente.

## Universo de Candidatos — embudo de dos etapas (vigente)

El framework de screening define **criterios** de selección pero no el **universo** sobre el
que se aplican. Investigar con LLM + web search cada acción del mercado no es viable.

**Descartado como ÚNICA fuente:** una watchlist de 30-50 tickers curada a mano — introduce
sesgo hacia nombres ya populares y eficientemente valuados, lo opuesto a lo que busca la
estrategia.

**Matizado el 2026-10-11:** LP propone ir dando nombres que le interesan o que le vayan
sonando, para acotar cuántas empresas hay que investigar. Implementado como un origen más de
`candidate_queue`: `source='interes_lp'`, prioridad 70, vía
`scripts/enqueue_news_candidate.py --source interes_lp`.

Esto **no** revierte la decisión anterior, y la diferencia importa: los nombres de LP son una
fuente adicional, no el universo. El embudo cuantitativo y la rotación siguen corriendo como
contrapeso, para que el agente mire ocasionalmente empresas que nadie le sugirió. Un nombre
propuesto entra al **embudo**, no a la cartera: pasa las mismas tres etapas y se descarta
igual que cualquier otro si falla Etapa 1.

- [ ] **Qué vigilar:** si la cola se llena de `interes_lp` y la rotación del universo nunca
      llega a consumirse, el sesgo hacia nombres ya populares volvió por la puerta de atrás —
      que es exactamente lo que la decisión original quería evitar. La señal de alarma no es
      el mecanismo, es la **proporción**: si pasan semanas sin que se analice un solo nombre
      de `rotacion_universo`, hay que reservarle cupo explícito en cada ciclo.

**Vigente — embudo de dos etapas:**
1. **Filtro cuantitativo objetivo (sin juicio humano):** acciones listadas en EE.UU. vía el
   screener de Nasdaq + cortes cuantitativos (market cap mínimo, cobertura mínima de
   analistas) — sin que ningún humano elija cuáles quedan dentro.
2. **Lote rotativo de descubrimiento:** cada semana, research profundo sobre un lote nuevo
   de ese pool, además de la revisión de lo que ya está en cartera.

### Etapa 1 revisada — ✅ **cerrada el 2026-10-11**

El pool se construía como la intersección de **constituyentes del S&P 500** con
**market cap ≥ $10B**. Eso dejaba ~400 nombres que *son* el índice casi completo por peso, y
el piso de $10B excluía todo el mid-cap por construcción.

Buscar alpha contra el S&P 500 eligiendo exclusivamente dentro del S&P 500 es contradictorio
con la misión: el alpha tendría que venir solo de ponderación y timing, nunca de selección.
En palabras de LP: *"si solo buscamos en el S&P 500 estaremos replicándolo casi todo el
tiempo"*.

- [x] **La pertenencia a un índice ya no es criterio de elegibilidad.**
      `build_quantitative_pool()` ya no intersecta con ningún índice; el parámetro
      `index_constituents` queda opcional y solo se aplica si
      `requiere_pertenencia_indice: true`, para no perder la capacidad de revertir.
- [x] **Piso de market cap: $2B.** Se evaluó $1B y se descartó **con datos**: bajo $1B hay
      3,060 nombres (53% del universo), de los cuales 23% es salud —mayoría biotech en fase
      clínica sin producto— y 18% finanzas entre bancos comunitarios y vehículos tipo SPAC.
      Estimación honesta: solo 2-5% pasaría un test serio de foso, y de esos buena parte tiene
      el mercado estructuralmente limitado. **Un foso sin pista no compone.** Bajar a $1B
      sumaba 555 nombres sin subir la tasa de acierto, con el mismo costo de research por
      nombre. El terreno fértil es el mid cap ($2B-$50B, ~1,824 nombres): negocios reales con
      historia financiera, menos saturados de analistas que las mega caps, y estructuralmente
      subrepresentados en un índice ponderado por capitalización.
      **Pool resultante verificado en vivo: 1,681 nombres.**
- [x] **Cobertura de analistas de 5 a 3.** Exigir 5 reintroducía por la puerta de atrás el
      mismo sesgo hacia nombres ya seguidos de cerca que se acababa de eliminar.
- [x] **Fuente de la lista base resuelta:** `fundamentals.get_us_stocks_with_market_cap()`
      sobre `api.nasdaq.com/api/screener/stocks` (~7,000 acciones US; 4,208 tras descartar
      units, warrants y preferentes por forma del ticker). Se descartaron dos alternativas,
      ambas verificadas el 11-oct: el API de screener de stockanalysis.com está detrás de
      Cloudflare (devuelve el challenge "Just a moment...") y el CSV de holdings de iShares
      (IWV/Russell 3000) devuelve una interstitial HTML en vez del archivo. El endpoint de
      Nasdaq **exige User-Agent de navegador**; con el UA del bot responde 403.
      `get_sp500_with_market_cap()` se conserva, ya no como lista base.
- [x] **Regla anti-replicación** escrita en el prompt del barrido diario: las mega caps más
      pesadas del índice son el peor lugar para buscar brecha, por ser el segmento más
      cubierto y mejor valuado del mercado.

**Consecuencia de diseño que esto destapó, y que hay que mirar de frente.** Con 2,127 nombres
elegibles (1,681 tras el piso) y 8 por semana, una barrida completa del pool tarda años. El
lote rotativo deja de ser un mecanismo de **cobertura** y pasa a ser **muestreo**.

La respuesta no es subir el lote —eso es lo que hacía morir el ciclo por timeout— sino
reconocer que el descubrimiento ya se movió de lugar: el rediseño Carlson dice textualmente
que *"la watchlist deja de ser accesoria: es el mecanismo central"*. El motor real es el
**barrido diario de noticias** que alimenta `candidate_queue`; la rotación es un goteo de
fondo que garantiza que el agente mire ocasionalmente fuera de lo que las noticias le ponen
enfrente. Queda documentado así a propósito, para que nadie lo lea como un bug de cobertura.

- [ ] **Pendiente del usuario:** si en algún momento se quieren ADRs internacionales, es
      cambiar `solo_listadas_en_eeuu` a `false`. Costo: otros estándares contables, riesgo de
      divisa y fiscalidad de dividendos más difícil de modelar.

## Framework de evaluación de empresas (Carlson)

Revisado el 7-oct a pedido del usuario, para pegarse lo más posible al método de Joseph
Carlson. Fuentes: su "Stock Checklist" (ene 2021) y el documento del "Edge" (ago 2023, versión
más reciente). Criterios eliminatorios acordados: **ROIC > WACC** y **pricing power**; moats
difíciles de replicar; concentración en calidad, 8-12 nombres.

- [x] **Regla 0 del screening** (commit `a879fd1`): verificar qué negocio es la empresa **hoy**
      antes de opinar — evita tesis construidas sobre una descripción obsoleta del negocio.
- [ ] Resto del checklist de Carlson cableado en el framework de screening del prompt.
- [ ] Metodología de valuación al estilo Carlson (pendiente: el detalle se quedó a medias
      cuando la conversación del 7-oct se movió a infraestructura).

## Lo construido y cerrado

### Pipeline de datos ✅
- [x] Embudo de dos etapas (`src/data/universe.py`): filtro cuantitativo + lote rotativo
      semanal circular, con verificación de cobertura de analistas aplicada de forma perezosa
      (solo al lote de la semana, no al pool completo, para no gastar cuota de API).
- [x] Cliente FMP (`src/data/fundamentals.py`) — API "stable", no la v3 legacy.
- [x] **Scraping de respaldo:** FMP devuelve 402 en bastantes endpoints por ticker
      (quote/key-metrics/ratios/analyst-estimates). Se reemplazaron con scraping con
      degradación por sector en vez de crash (commits `8322b8e`, `3cd7476`, `82de4ba`,
      `e410d40`).
- [x] **Yahoo Finance como segunda fuente** (`src/data/yahoo.py`), con respaldo campo por
      campo (commit `12b5514`).
- [x] Benchmark (`src/data/market.py`): precio actual y retorno histórico del S&P 500
      (`^GSPC`) para la métrica de alpha relativo.
- [x] Caché JSON invalidada por día (`src/data/cache.py`); config centralizada
      (`src/config.py`) que falla claro si falta `FMP_API_KEY`.
- **Verificación:** lógica pura del embudo probada con datos sintéticos —
  `scripts/test_universe_logic.py`, 11/11. Integración en vivo: `scripts/smoke_test_fmp.py`.

### Guardrails ✅
- [x] `src/guardrails/validator.py`, código puro sin I/O: `validate_trade_proposal()` valida
      15% máximo por posición, sin operaciones intradía, cash suficiente, universo restringido
      a acciones, máximo de posiciones (no bloquea agregar a una ya existente), y bloquea
      comprar más de una posición marcada para revisión de tesis (pero permite venderla —
      salir siempre está permitido). `check_thesis_review_triggers()` flaguea posiciones en
      -20% o peor sin vender automático. 20/20 tests pasando
      (`scripts/test_validator_logic.py`).
- [x] **Decisión documentada:** el mínimo de 8 posiciones es *warning*, no bloqueo — bloquear
      una venta por invalidación de tesis para sostener un conteo mínimo sería la misma regla
      ciega que el proyecto ya rechazó.
- [x] **Cartera heredada, resuelto por una vía distinta a la prevista.** La preocupación era
      que VOO al 28.8% violara el tope de 15%. Dejó de aplicar: LP decidió el 11-oct que el
      mandato de Ataraxia y la medición de alpha cubren **solo las equities**, así que los ETFs
      amplios quedan fuera del mandato y no son un incumplimiento. El validator ya contaba la
      concentración solo sobre acciones (commit `30e02bd`, con test:
      *"ETFs excluidos de conteo, incluidos en denominador de cartera real"*). Los triggers de
      −20% sobre lo heredado sí operan, y hoy disparan correctamente para IREN (−29.15%) e
      INFQ (−30.95%).
- [x] **Kill-switch de drawdown ACTIVO en −30%** (decisión de LP, 11-oct). Estaba en `None`
      por la fase paper que ya no existe. Se eligió −30% y no −25% porque con 8-15 nombres
      concentrados un 25% entra en el ruido normal de un mercado bajista, y un freno que se
      dispara por ruido detiene al agente justo cuando las oportunidades son mejores. **Bloquea
      compras nuevas a nivel fondo; nunca fuerza ventas** — eso sería la regla ciega que
      `PROJECT_PLAN.md` rechaza. Cinco tests nuevos cubren el umbral, incluido que −25% NO
      dispara.
- [x] **Comprar más de una posición existente es un veredicto válido y esperado.** El prompt
      del ciclo lo dice explícitamente: al revisar una posición el veredicto tiene **tres**
      salidas —agregar, sostener, salir— con cantidad concreta. El guardrail nunca bloqueó
      sumar a una posición existente mientras el resultado no pase el 15% al costo; lo que
      faltaba era que el prompt no lo presentara como opción.

### Base de datos ✅
- [x] **Supabase (Postgres)**, no SQLite — para permitir acceso remoto (dashboard). Tablas:
      `decisions`, `positions`, `performance`, `universe_state`.
- [x] **Schema versionado en Git** (`ataraxia/supabase/migrations/`), desplegado vía la
      integración de GitHub de Supabase. Ver `ataraxia/supabase/README.md`.
- [x] Conexión `psycopg2` con rol dedicado `ataraxia_brain`, no `supabase-py` (cuyas keys
      anon/service_role rompen el principio de scope mínimo). `ataraxia_brain` solo puede
      insert/select en tablas de log y select/update en `universe_state`. El `CREATE ROLE` con
      password se hace a mano, **nunca en una migración versionada**.
- [x] Resiliencia: escrituras fallidas se encolan en `data/pending_db_writes/` y
      `flush_pending_writes()` reintenta al inicio de cada corrida.
- [x] **Verificado en vivo** (`scripts/verify_db_connection.py`): conexión OK, lectura de
      `universe_state` OK, insert/select en `decisions` OK, y `ataraxia_brain` **no puede**
      hacer `DELETE` ni `CREATE TABLE` — scope mínimo real, no solo en el papel.

### El brain
- [x] System prompt/personalidad (`src/agent/prompt.py`) — tono Carlson + razonamiento
      estilo The Claude Portfolio + conciencia de guardrails.
- [x] Herramientas invocables por bash (`scripts/brain_portfolio.py`,
      `brain_candidates.py`, `brain_fundamentals.py`, `brain_decide.py`) — implementadas y
      probadas. La orquestación la hace la automatización, no un harness propio.
- [x] `brain_portfolio.py` y los demás scripts leen el portafolio real desde Supabase vía
      `portfolio_csv.load_latest()`. `src/reporting/portfolio.py` →
      `build_portfolio_state()` (que leía la DB del fondo simulado) quedó sin usarse.

## Roadmap vigente (plan acordado el 7-oct)

### Fase 0 — Desbloquear ✅
- [x] iCloud destrabado.

### Fase 1 — Infraestructura ✅
- [x] **Repo movido fuera de iCloud: vive en `~/ataraxia`** (movido el 7-oct a las 19:41).
      El destino acordado originalmente era `~/code/`; terminó en la raíz del home.
- [x] Cerrada la fuente de verdad del portafolio (ver sección correspondiente).
- [ ] **Pendiente del usuario, y es una trampa activa:** la copia obsoleta del repo sigue en
      `~/Documents/Claude/Projects/Financial Agent/ataraxia`, con código de agosto (`src/`
      sin tocar desde el 23-ago) y sin los últimos commits. Ya nada apunta ahí, pero es
      exactamente lo que causó un diagnóstico falso el 8-oct. Renombrarla a
      `ataraxia-OBSOLETO` o mandarla a la basura.

### Fase 2 — Personalidad y framework
- [x] Rediseño de personalidad y framework Carlson de tres etapas (riesgo y foso / checklist /
      valuación), con ROIC > WACC, pricing power y caso del atacante como eliminatorios.
- [ ] Metodología de valuación al estilo Carlson, que quedó a medias.

### Fase 3 — Las dos automations ✅
- [x] **Automation de ciclo:** `ataraxia-daily-brain` / "Ataraxia — ciclo lun/mié
      pre-apertura", cron `30 6 * * 1,3` en `America/Guatemala`, agente `ataraxia`, sesión
      aislada, anuncio por WhatsApp.
      **Reparada el 11-oct** tras 5 fallos consecutivos por timeout. Tres causas, en orden de
      importancia: (1) apuntaba a la **copia obsoleta del repo** en Documents, así que habría
      ejecutado código de agosto; (2) el lote de 18 tickers no cabía en 60 minutos — y el
      cuello **no eran los scripts** (`brain_fundamentals.py` tarda 2.4 s por ticker,
      cronometrado) sino el razonamiento del modelo; (3) no tenía instrucción de entregar
      parcial. Ahora: ruta `~/ataraxia`, timeout 90 min, lote de 8, y corte a los 75 min con
      entrega de lo que tenga. ⚠️ `consecutiveErrors` sigue en 5 y solo se reinicia con una
      corrida exitosa: si falla el 12-oct, el job puede auto-deshabilitarse.
- [x] **Automation diaria de barrido de noticias:** `ataraxia-news-sweep`, cron
      `45 5 * * 1-5`. A las 5:45 y no a las 6:00 para no solaparse con el ciclo de 6:30 — la
      contención de sesiones es la causa documentada de fallos previos (ver "Riesgos
      cerrados"). Encola en `candidate_queue` (tabla de Supabase, no un `candidates-queue.md`
      como decía el plan original). Criterio explícito de 0 a 3 por día, con cero declarado
      como el resultado más común y correcto.
- [x] **Pieza que faltaba:** `candidate_queue` admitía `source='noticia'` desde el rediseño
      Carlson pero **ningún código la producía**. Nuevo `scripts/enqueue_news_candidate.py`,
      que rechaza motivos de menos de 40 caracteres a propósito: un encolado que solo repite
      el titular no le dice nada al reporte que lo consume.
- [ ] **Pendiente del usuario:** el barrido corre como agente `main`, no `ataraxia`. La
      herramienta de automations rechaza cambiar el agente desde el alcance del asistente
      (`agentId cannot be changed by caller scope`). Se arregla con
      `openclaw automations edit a94c07cb-284f-47db-9c3b-c07db148c15a --agent ataraxia`
      o desde la página de Automations del Control UI.
- [ ] **Pendiente de decisión:** ¿el ciclo de análisis pasa a diario (`30 6 * * 1-5`) o se
      queda en lunes y miércoles? El barrido ya es diario. Costo de pasar a diario: cada
      corrida es hasta 90 min de Opus, así que multiplica el gasto por 2.5.

### Fase 4 — Dashboard
*Construir después de tener datos reales — un dashboard vacío no ayuda a decidir nada de
diseño.*
- [ ] Gráfico de **retorno de Ataraxia vs. S&P 500** (el entregable central: es la misión
      hecha visible), tabla de transacciones con rationale completo, feed de resúmenes,
      distribución del portafolio, métricas (Sharpe, drawdown).
- [ ] HTML estático generado localmente es suficiente dado el volumen de datos.
- [ ] Accesible desde el teléfono — requisito mencionado por el usuario, define si basta HTML
      local o hace falta exponerlo.

### Criterio de evaluación

**Decidido el 11-oct — el alpha se mide SOLO sobre las equities**, no sobre los ETFs amplios
(VOO/SCHD/VXUS). Razón: son ancla pasiva fuera del mandato del agente, y VOO *es* el
benchmark — incluirlo arrastra la medición hacia el índice y esconde el aporte real de
Ataraxia. Implementado en `asset_class` (tabla `portfolio_lots`),
`LotSnapshot.equities_only()` y documentado en `src/reporting/performance.py`.

Al 8-oct, con esa definición: **equities +8.85%** (costo $6,272.00 → valor $6,826.95) contra
el +14.75% del total de la cuenta, que incluye los ETFs. El 8.85% es el número que se compara
contra el S&P 500.

- [ ] **Pendiente del usuario:** redefinir qué significa "Ataraxia funciona" sin fase de paper
      trading. El criterio anterior era un gate para pasar de paper a capital real, y ese
      puente ya no existe. Falta la ventana mínima de medición y el criterio de muerte
      (`PROJECT_PLAN.md` fija el principio: alpha consistentemente negativo ⇒ liquidar y pasar
      a indexación pasiva).
- [ ] **Cartera sombra — mitigación acordada, no implementada.** Como la ejecución es manual,
      lo que se mide por defecto es "Ataraxia + el veto de LP", no Ataraxia. La pieza existe:
      `carlson.record_lp_action(recommendation_id, action, ...)` cierra el ciclo registrando
      qué hizo LP con cada recomendación. Falta el cálculo que reconstruya las dos series
      —real y sombra— y las compare contra el S&P 500. Sin eso, la pregunta central del
      proyecto no tiene respuesta atribuible.

## Deuda técnica de la migración — ✅ **código huérfano eliminado**

Verificado el 11-oct contra el repo vivo: `src/executor/`, `src/broker/` y `docker/` **ya no
existen** (borrados en commit `40b0db0`, "Limpiar executor automatizado, cliente IBKR y smoke
tests de FMP"). `src/agent/tools.py` y `loop.py` tampoco. Las referencias a paper trading
quedaron en dos archivos y se limpiaron: `performance.py` (corregido) y `prompt.py`, donde la
mención se conserva porque dice lo correcto — *"El portafolio de LP es real — es su dinero, en
Schwab. No es paper money"*.

Lo que sigue en pie y no molesta:

- **Tablas del executor en la DB:** `executed_trades`, `cash_events` y el rol
  `ataraxia_executor` todavía existen en Supabase (migración
  `20260727120000_executor_tables.sql`). Ya nadie las escribe ni las lee en el flujo del
  brain. Borrarlas requiere DDL con credenciales de admin; no hay apuro ni riesgo en dejarlas.
- `src/db/schema.sql` — ya no es fuente de verdad, apunta a `supabase/migrations/`.
- `src/reporting/portfolio.py` → `build_portfolio_state()` quedó sin usarse al migrar el brain
  a `load_latest()`. Es el último resto del fondo simulado; se puede borrar sin consecuencias.

## Estructura de Repositorio

*El repo vive en `~/ataraxia` y su raíz es la raíz del repo de Git.*

> **`PROJECT_PLAN.md` y `BUILD_PLAN.md` viven dentro del repo, en `docs/`, desde el
> 2026-10-11.** Antes estaban fuera, en `~/Documents/Claude/Projects/Financial Agent/`, por
> decisión explícita del usuario — y nada los obligaba a mantenerse al día: se desactualizaron
> dos veces en cuatro días (8-oct y 11-oct), describiendo como pendiente trabajo ya hecho y
> como vigente arquitectura ya descartada. Versionarlos con el código los pone en el mismo
> commit que el cambio que documentan, que es la única forma de que no se separen.

Rama de trabajo: `redesign-carlson`, mergeada a `main` el 11-oct. **El merge a `main` es lo
que dispara el despliegue de migraciones** vía la integración de GitHub de Supabase — una
migración que solo existe en local o en una rama no se aplica nunca (eso costó una confusión
el 11-oct). Verificado: el despliegue tardó menos de 40 segundos.

```
~/ataraxia/                   # raíz del repo de Git
├── .env                      # secretos (FMP, Supabase), no en git
├── config/
│   └── universe.yaml         # embudo: piso $2B, sin requisito de índice, lote de 8
├── supabase/
│   ├── config.toml
│   ├── README.md             # setup (rol ataraxia_brain, integración GitHub)
│   └── migrations/           # schema versionado — SIN CREATE ROLE/password
├── src/
│   ├── agent/
│   │   └── prompt.py         # personalidad + framework Carlson de tres etapas
│   ├── guardrails/
│   │   └── validator.py      # validación determinista; kill-switch en -30%
│   ├── data/
│   │   ├── fundamentals.py   # FMP + scraping + screener de Nasdaq (lista base)
│   │   ├── yahoo.py          # segunda fuente, respaldo campo por campo
│   │   ├── market.py         # precios + benchmark ^GSPC
│   │   ├── universe.py       # embudo de dos etapas + RotationState
│   │   ├── portfolio_csv.py  # PortfolioSnapshot; load_latest() prefiere la DB
│   │   ├── schwab_lots.py    # parser de los "Lot Details" por ticker
│   │   └── cache.py          # caché JSON, invalidada a diario
│   ├── reporting/
│   │   ├── portfolio.py      # resto del fondo simulado, ya sin uso
│   │   └── performance.py    # alpha vs ^GSPC, Sharpe, drawdown
│   ├── db/
│   │   ├── models.py         # psycopg2, snapshots/lotes, PORTFOLIO_EPOCH
│   │   └── carlson.py        # watchlist, candidate_queue, recommendations
│   └── data/
├── data/
│   └── schwab-lots/2026-10-08/   # los 16 exports de Lot Details del corte
├── dashboard/
│   └── index.html
└── scripts/
    ├── brain_portfolio.py          # herramientas que el brain invoca por bash
    ├── brain_candidates.py
    ├── brain_fundamentals.py
    ├── brain_decide.py
    ├── brain_watchlist.py
    ├── enqueue_news_candidate.py   # encola desde el barrido de noticias
    ├── load_portfolio_snapshot.py  # carga un corte de Schwab a Supabase
    ├── run_cycle.py
    ├── compute_performance.py
    ├── log_recommendation.py       # reemplaza log_manual_trade
    └── test_*.py / dry_run_check.py / verify_db_connection.py
```

## Stack Técnico Confirmado
- **Orquestación del brain:** automatización programada de OpenClaw (local), no un script
  standalone llamando a la API
- **Ejecución:** manual (usuario), permanente — sin broker API
- **Cuenta:** Charles Schwab (real), acceso de solo lectura
- **Datos fundamentales:** Financial Modeling Prep (tier gratis) + scraping de
  stockanalysis.com como respaldo + Yahoo Finance como segunda fuente campo por campo
- **Lista base del universo:** screener de `api.nasdaq.com` (requiere UA de navegador)
- **Benchmark:** `^GSPC` vía FMP
- **DB:** Supabase (Postgres), `psycopg2` con rol `ataraxia_brain`. El portafolio real vive en
  `portfolio_snapshots` + `portfolio_lots`, versionado por fecha de corte
- **Dashboard:** HTML estático, leyendo de Supabase

## Riesgos cerrados

**Hosting del brain — CERRADO (2026-09-07).** El riesgo era que una sesión *programada* de
Cowork no tuviera la conectividad de red de la interactiva (el sandbox bloqueó un intento de
conectar a Supabase). Se resolvió cambiando de host, no configurando el sandbox: OpenClaw
corre en la máquina del usuario, con la misma red que ya se usó para conectar a Supabase.
Verificado con corridas reales: el ciclo completo (portfolio → candidatos → fundamentals →
decide) corrió en ~3 minutos y escribió decisiones en Supabase desde una sesión programada,
sin intervención.

**Entrega del resumen — CERRADO (2026-09-07).** El gateway no tenía canal externo instalado,
así que `announce` fallaba con `Channel is required` y el resumen moría en la sesión del cron.
Resuelto ligando el job a una sesión persistente dedicada (`delivery.mode: none`): el resumen
se commitea a esa sesión sin necesitar canal. Verificado end-to-end, corrida `ok` en 275s.

**Lección operativa.** Los fallos de `isolated agent setup timed out before runner start` eran
**contención de sesión**, no configuración: se producían al forzar corridas manuales mientras
`agent:main:main` estaba ocupada con un turno interactivo. No forzar `automations run` de este
job desde el chat principal mientras haya un turno activo — cada fallo incrementa
`consecutiveErrors` y puede auto-deshabilitar el job. Por la misma razón el barrido de
noticias quedó a las 5:45 y no a las 6:00: con timeout de 30 minutos se habría solapado con el
ciclo de 6:30.

**Dos copias del repo — CERRADO el 2026-10-11, y la lección vale más que el bug.** El 8-oct se
produjo un diagnóstico completamente falso: se reportó que faltaba el lector del CSV de Schwab
y que `build_portfolio_state()` leía el fondo simulado, concluyendo que era "el bloqueador real
del proyecto". Todo eso era cierto de la copia en `~/Documents/.../ataraxia`, cuyo `src/` no se
tocaba desde el 23-ago — y falso del repo vivo en `~/ataraxia`, que iba tres commits adelante y
ya tenía `portfolio_csv.py` desde el 7-oct. La automation también apuntaba a la copia vieja.

Qué hacer distinto: **verificar en qué copia se está antes de concluir algo sobre el estado del
proyecto.** `git log --oneline -1` y la fecha de modificación de `src/` lo resuelven en
segundos. Un diagnóstico sobre el árbol equivocado no es un error menor: produce conclusiones
confiadas y completamente invertidas.

## Estado al 2026-10-11 y próximo paso

**El sistema está operativo.** Las dos automations existen y están habilitadas, el portafolio
real está en Supabase, el brain lo lee, los guardrails corren contra datos actuales y la cola
tiene tres nombres listos para el ciclo del lunes 12 (UBER y SPGI como posiciones abiertas
nunca pasadas por Etapa 1, NFLX como idea nueva).

**El riesgo vivo:** `ataraxia-daily-brain` arrastra `consecutiveErrors: 5`, que solo se
reinicia con una corrida exitosa. La corrida del lunes 12 a las 6:30 es la prueba de que la
reparación funcionó. Si vuelve a fallar, el job puede auto-deshabilitarse y hay que
rehabilitarlo a mano.

Pendiente del usuario, en orden de impacto:

1. **¿Ciclo diario o lunes y miércoles?** El barrido de noticias ya es diario. Pasar el
   análisis a diario multiplica el costo de Opus por 2.5.
2. **Hacer que el barrido corra como `ataraxia`:**
   `openclaw automations edit a94c07cb-284f-47db-9c3b-c07db148c15a --agent ataraxia`.
3. **Definir el criterio de evaluación** sin fase de paper trading: ventana mínima y criterio
   de muerte.
4. **Renombrar o borrar la copia obsoleta del repo** en
   `~/Documents/Claude/Projects/Financial Agent/ataraxia`. Es la trampa que ya causó un
   diagnóstico falso.
5. **Borrar la fila de prueba** `as_of 1999-01-01` de `portfolio_snapshots` (hoy filtrada en
   lectura, no urgente).

Pendiente de construir, en orden:

1. **Cartera sombra** — el cálculo que separa el aporte de Ataraxia del veto humano. Sin eso,
   la pregunta que define el proyecto no tiene respuesta atribuible.
2. **Dashboard** (Fase 4) — con dos snapshots en la DB ya hay serie que graficar; el
   entregable central es Ataraxia vs. S&P 500.
3. **Metodología de valuación de Carlson**, que quedó a medias el 7-oct.
4. **Limpieza menor:** borrar `src/reporting/portfolio.py` y, si se quiere, las tablas del
   executor en Supabase.
