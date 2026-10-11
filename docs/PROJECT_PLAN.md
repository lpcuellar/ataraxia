# Proyecto: Ataraxia — Agente de Inversión con IA

*Última actualización: 11 de octubre, 2026*

## Misión (propósito único)

**Ataraxia existe para vencer al S&P 500 en el largo plazo. Nada más.**

Esa es la única razón de ser del agente. Todo lo demás en este documento — la personalidad
estoica, los guardrails, la cadencia diaria, la arquitectura, el dashboard — son *medios*
subordinados a ese fin, no fines en sí mismos. Si una decisión, una feature o una posición no
aumenta la probabilidad de superar al índice de forma sostenida, no pertenece al proyecto.

Consecuencias que se derivan directamente de esta misión:

- **El éxito tiene una sola definición:** retorno acumulado de Ataraxia − retorno acumulado
  del S&P 500 (total return, dividendos reinvertidos) > 0, de forma sostenida y en horizontes
  largos (medición primaria a 3+ años; las ventanas cortas son informativas, no veredictos).
- **"Ganar dinero" no es ganar.** Un año de +18% es un fracaso si el índice hizo +25%. Un año
  de −12% es un éxito si el índice hizo −20%. El número absoluto nunca es la métrica.
- **Replicar el índice es fracasar por definición.** Si la cartera converge en composición y
  comportamiento al S&P 500, Ataraxia no tiene propósito — el mismo resultado se consigue
  comprando VOO sin agente, sin costo y sin riesgo de ejecución. La concentración y la
  diferenciación respecto al índice no son un efecto secundario tolerado: son el requisito.
  Esto incluye la exposición indirecta — un peso alto en ETFs amplios diluye el mandato.
- **El listón es alto y honesto.** La mayoría de los gestores profesionales no le ganan al
  S&P 500 a 10+ años. Asumimos esa dificultad de frente: se mide sin excusas, se reporta el
  delta aunque sea negativo, y se acepta que el veredicto puede ser que Ataraxia no funcionó.
- **Criterio de muerte del proyecto:** si tras el período de evaluación acordado el alpha es
  consistentemente negativo, la conclusión correcta es liquidar Ataraxia y pasar a indexación
  pasiva. El proyecto debe poder fallar; un experimento que no puede perder no mide nada.

## 0. Nombre del Agente: Ataraxia
**Ataraxia** (ἀταραξία): término estoico/epicúreo para la calma inalterable — un estado que
no se perturba por ruido externo. Se eligió porque describe literalmente el rasgo de
personalidad central que definimos: no reacciona a titulares, miedo o FOMO, y mantiene la
tesis mientras el negocio subyacente siga intacto. Verificado sin colisión con fondos de
inversión, agentes de IA o brands existentes (a diferencia de "Kairos" y "Sophrosyne", que sí
colisionaban con firmas reales).

## 1. Definición del Problema y Métricas

### Objetivo
Desarrollar **Ataraxia**, un agente de IA que gestione un fondo de inversión pequeño
(prueba/experimento), replicando el enfoque de **The Claude Portfolio** (@theaiportfolios /
AI Finance Labs — ver Estrategia de Referencia abajo): selección de acciones vía análisis
fundamental/valuation (no técnico), con razonamiento probabilístico transparente, sin day
trading, con guardrails estrictos definidos por el usuario. Estrategia **long-only, orientada
a largo plazo**, con **revisión diaria** (no trading diario — ver Sección 2).

### Benchmark
- El agente se evalúa exclusivamente comparándose contra el **S&P 500** en el mismo período.
- Dashboard debe mostrar retorno del agente vs. retorno del benchmark lado a lado.

### Alcance de la medición — decidido el 2026-10-11

**El alpha se mide SOLO sobre las equities del portafolio, no sobre los ETFs amplios**
(VOO/SCHD/VXUS). Decisión de LP.

El razonamiento: esos ETFs son ancla pasiva que existía antes de Ataraxia y queda fuera de su
mandato, y VOO *es* el benchmark. Incluirlos arrastraría la medición hacia el índice y
esconderia el aporte real del agente — un portafolio con un tercio en VOO empata con el S&P
500 en ese tercio por construcción, lo que infla o amortigua el resultado sin que el agente
haya decidido nada.

Consecuencia práctica: el tope de 15% por posición y el conteo de concentración **no aplican
a los ETFs**. VOO al 28.8% de la cuenta no es un incumplimiento, es un activo fuera del
mandato.

Al 2026-10-08, con esta definición: **equities +8.85%** (costo $6,272.00 → valor $6,826.95),
contra +14.75% del total de la cuenta. El 8.85% es el número que compite contra el índice.

### Métricas de Éxito
- **Alpha relativo (métrica principal):** retorno acumulado del agente − retorno acumulado
  del S&P 500 en la misma ventana de tiempo. No hay un target absoluto — el único objetivo
  es que el delta sea positivo de forma sostenida.
- Sharpe ratio (retorno ajustado al riesgo)
- Máximo drawdown
- Win rate de operaciones

**Problema de atribución a resolver (ver `BUILD_PLAN.md`).** Como la ejecución es manual, lo
que se mide por defecto es "Ataraxia + el veto de LP", no Ataraxia. Si LP declina 6 de 20
propuestas, el resultado final es compatible con "el veto ayudó" y con "el veto costó", sin
forma de distinguirlas. Mitigación acordada: registrar también lo declinado y modificado, para
reconstruir dos series —la **real** (lo que LP hizo) y la **sombra** (lo que Ataraxia habría
hecho sin filtro)— y comparar ambas contra el S&P 500.

### Guardrails (No Negociables) — revisados para estrategia concentrada de largo plazo
- **Stop por invalidación de tesis (reemplaza "2% pérdida por operación"):** un stop fijo de
  2% es una construcción de day trading, incompatible con posiciones de convicción a largo
  plazo. En su lugar: cada posición tiene una tesis fundamental explícita al entrar (backlog,
  valuation gap, poder de fijación de precios), con un **bear case explícito y su
  probabilidad estimada** (al estilo The Claude Portfolio). Una caída de **-20% desde costo**
  dispara una revisión obligatoria de tesis (no una venta automática).
- **Máximo 15% de posición individual al costo** (reemplaza "mínimo 3 activos"): la
  diversificación real en una estrategia concentrada viene de limitar el tamaño máximo por
  posición, no de un mínimo débil de 3 activos. Cartera objetivo: **8–15 posiciones**
  (revisado desde 8–12). Se cuenta **solo sobre equities** — un ETF de índice ya es una
  canasta diversificada y no suma riesgo idiosincrático.
- **Agregar a una posición existente es una recomendación válida y esperada.** Al revisar una
  posición, el veredicto tiene tres salidas: agregar, sostener o salir. El guardrail no
  bloquea sumar mientras el resultado no pase el 15% al costo. No hace falta un nombre nuevo
  para desplegar cash; Carlson compra más de lo que ya conoce cuando el precio se presenta.
- **Máximo drawdown del fondo — ACTIVO en −30% desde el 2026-10-11.** La redacción anterior
  («sin kill-switch durante paper trading, se introduce 25–30% cuando haya capital real»)
  quedó obsoleta: no hay fase de paper y el capital real está en juego desde el día uno.
  Se eligió **−30% y no −25%** porque con 8–15 nombres concentrados un 25% entra en el rango
  de ruido de un mercado bajista normal, y un freno que se dispara por ruido detiene al agente
  exactamente cuando las oportunidades son mejores. **Bloquea compras nuevas a nivel fondo;
  nunca fuerza ventas** — eso sería la regla ciega que este plan rechaza. El control de riesgo
  por posición sigue siendo el trigger de −20% atado a la tesis.
- **Sin operaciones intradía (no same-day round-trips)** — coherente con el enfoque
  buy-and-hold concentrado.
- **Revisión diaria, trading no-diario.** Implementado como **dos automations separadas**
  (2026-10-11): el **barrido de noticias** corre de lunes a viernes a las 5:45 y solo encola
  candidatos; el **ciclo de análisis profundo** corre lunes y miércoles a las 6:30, consume la
  cola de a 2–3 nombres y es el único que propone. Así la vigilancia es diaria sin pagar el
  costo de un análisis profundo diario. *(Pendiente de decisión: si el ciclo pasa a diario,
  multiplica el gasto de modelo por 2.5.)* El agente solo propone cuando hay un catalizador
  fundamental real — no por calendario ni por necesidad de "hacer algo". En días sin acción
  publica una línea diciéndolo.
- Universo: **solo acciones** (sin crypto, sin prediction markets). Desde el 2026-10-11, **sin
  restricción de índice**: cualquier acción listada en EE.UU. con market cap ≥ $2B es
  elegible. Buscar alpha contra el S&P 500 eligiendo solo dentro del S&P 500 obliga a que el
  alpha venga de ponderación y timing, nunca de selección — contradice la misión. Ver el
  detalle y los datos que respaldan el piso de $2B en `BUILD_PLAN.md`.
- Cada transacción debe ser logueada y reportada al usuario: rationale pre-trade (tesis +
  bear case + probabilidad) y justificación post-trade (¿la tesis se mantiene?).

## 2. Arquitectura del Agente
- [x] **Decidido:** sin LangChain ni CrewAI. Ataraxia es un solo analista con un loop
      (revisar → investigar → decidir → loguear), no un equipo multi-agente.
- [x] **Hosting y orquestación: OpenClaw local, como automatización programada** (revisado el
      7-sep; ver Sección 6 para por qué se revirtió la decisión original de Cowork). No es un
      script standalone llamando a la API.
      La separación estricta se mantiene y es la propiedad de seguridad central: el **"brain"**
      hace research y razonamiento y escribe propuestas, y **no tiene ninguna ruta a mover
      dinero**; la **ejecución** es el propio usuario, a mano, de forma permanente.
- [x] **Decidido:** modelo = Claude — coherente con que toda la tesis de razonamiento
      (personalidad, framework de screening) está modelada sobre The Claude Portfolio, y
      Cowork ya corre sobre Claude directamente.
- [x] **Resuelto:** el flujo de decisión es **100% análisis fundamental/valuation**, no
      técnico. Flujo: universo de candidatos → screening fundamental (framework abajo) →
      decisión con rationale + bear case probabilístico → ejecución → justificación
      post-trade → log. Revisión diaria de tesis existentes (no implica trading diario).
- [ ] **Pendiente de decidir:** ¿se quiere una capa técnica ligera solo para *timing* de
      entrada (ej. no comprar en resistencia técnica), separada de la tesis de compra?
      Ninguna de las dos referencias la usa, pero es una opción, no una obligación.

### Personalidad y Voz del Agente
Combinación explícita de dos referencias, no genérico "asistente financiero":
- **Tono (Joseph Carlson):** calmado, sin reaccionar a titulares, miedo o FOMO. Cada
  decisión se enmarca como "¿es este un mejor negocio en 10 años?", no como ruido de corto
  plazo. Criterios de compra/venta explícitos y consistentes, no ad hoc. Enfoque en calidad:
  monopolio/ventaja competitiva, poder de fijación de precios, crecimiento orgánico, modelo
  de negocio capital-light.
- **Razonamiento (The Claude Portfolio):** cada posición lleva números concretos (backlog en
  $, % de crecimiento, múltiplo de valuation, retorno esperado) y un bear case explícito con
  probabilidad estimada — el agente argumenta honestamente en contra de sí mismo, no oculta
  la incertidumbre.
- **Cadencia de comunicación:** como los updates de Carlson (que reporta incluso en meses sin
  operaciones), el agente publica un resumen diario aunque no haya operado — el valor está en
  el razonamiento, no solo en la acción.

### Framework de Screening Fundamental — The Claude Portfolio (@theaiportfolios / AI Finance Labs)
Referencia correcta (corrige la versión anterior de este documento, que citaba un backtest
distinto de Lynn Raebsamen): portafolio en vivo desde abril 2026, ~$50,000 nocional,
comparado en vivo contra SPY. Rasgos verificados:
- **No es un screen puramente temático** — es análisis de valuation/calidad: busca la brecha
  más amplia entre precio de mercado y poder de compounding intrínseco (backlog, guidance de
  crecimiento, TAM, múltiplo forward)
- **Sizing por retorno esperado:** posiciones grandes (ej. 10%) cuando el retorno esperado
  modelado supera ampliamente al de la siguiente mejor idea (>20% vs. dígitos bajos)
- **No vende en pánico ante ruido macro:** compró Microsoft y Broadcom en medio de una caída
  geopolítica porque la compresión de múltiplo lucía como mispricing por miedo, no como tesis
  rota — mantuvo la posición mientras el negocio subyacente seguía intacto
  (backlog/crecimiento confirmados)
- **Diversificado por sector pero concentrado por convicción** (energía, salud,
  semiconductores, cloud, minería en su selección inicial de 15 activos) — no un solo tema
  como AI-infra puro
- **Transparencia pública:** cada posición tiene un bear case con probabilidad estimada
  explícita, y el agente responde públicamente a objeciones de otros (ej. riesgo de
  desintermediación de AI a un holding, estimado en 20% de probabilidad)
- **⚠️ Nota de riesgo:** es un experimento en vivo desde abril 2026, no un track record largo.
  El propio marco (comparar LLMs gestionando dinero) es parte del experimento, no una
  estrategia validada por años. Replicar el *método* (valuation + backlog + bear case
  probabilístico) tiene más sentido que replicar las posiciones exactas de @theaiportfolios
  en un momento dado.

## 3. Integración de APIs Financieras

> ⚠️ **Todo lo relativo a IBKR en esta sección quedó sin efecto el 7-oct.** No hay cuenta de
> IBKR, no hay API de broker y no habrá: la ejecución es manual en Schwab de forma permanente,
> y el código del cliente IBKR se borró del repo (commit `40b0db0`). Se conserva el registro
> de las decisiones por si alguna vez se reconsidera un broker automatizado.

- ~~Broker: **Interactive Brokers** (viable desde Guatemala, sin necesidad de SSN)~~
- ~~**Decidido:** usar **Client Portal (Web) API**, no TWS API — TWS API no puede correr
  headless (requiere GUI), incompatible con un agente autónomo~~
- ~~Wrapper de automatización tipo **IBeam** o **ibind** para el gateway~~
- ~~**Aceptado:** IBKR requiere 2FA para todas las cuentas individuales, sin excepción~~ —
  dejó de ser un problema al no automatizar la ejecución. Era uno de los argumentos de peso a
  favor de la ejecución manual.
- [x] **Decidido — Fuente de datos fundamentales:** combinación de API de datos financieros
      (números duros: múltiplos, crecimiento, márgenes) + web search del propio agente
      (contexto cualitativo: backlog, guidance, noticias) — igual a cómo opera The Claude
      Portfolio real. Falta elegir el proveedor de API específico (ver `BUILD_PLAN.md`, Fase 1).
- [ ] Revisar documentación: https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/

## 4. Base de Datos y Almacenamiento
- [ ] Decidir local vs. nube
- [ ] Diseñar schema para histórico de operaciones (incluyendo rationale pre-trade con bear
      case/probabilidad, y justificación post-trade de cada transacción)
- [ ] Implementar logging de decisiones del agente (incluyendo días sin operación, con resumen
      de revisión diaria)

## 5. Frontend y Visualización — Dashboard de Monitoreo
Página para chequear en tiempo real:
- [ ] Gráfico de retorno acumulado del fondo vs. S&P 500 (líneas superpuestas + delta/alpha)
- [ ] Tabla de últimas transacciones (rationale pre-trade con bear case/probabilidad, y
      justificación post-trade de cada una)
- [ ] Feed de resúmenes diarios (incluyendo días sin operación)
- [ ] Distribución actual del portafolio por activo (8–15 posiciones, con % del total), con
      los ETFs amplios separados de las equities — el alpha se mide solo sobre estas últimas
- [ ] Métricas de performance en tiempo real (Sharpe ratio, drawdown)
- [ ] Resumen de P&L diario

## 6. Hosting e Infraestructura
- [x] **Decidido y luego REVERTIDO — el brain NO corre en Cowork, corre en OpenClaw local.**
      La decisión original fue Cowork, descartando explícitamente OpenClaw/Hermes por
      superficie de ataque. Se revirtió el 7-sep por una razón concreta: **el sandbox de red
      de Cowork bloqueaba la conexión a Supabase** desde sesiones programadas. OpenClaw corre
      en la máquina del usuario con la red que ya funcionaba. Costo asumido: se perdió la
      promesa de "no hace falta que la laptop esté encendida" — si la máquina está apagada o
      dormida a la hora del job, ese ciclo no ocurre. Detalle en `BUILD_PLAN.md` →
      "Riesgos cerrados".
- [x] **Decidido — la ejecución es manual de forma PERMANENTE**, no durante una fase. No hay
      executor automatizado ni Fase 5: el código que lo implementaba se borró del repo.
      El brain no tiene ninguna ruta a mover dinero — no hay cuenta de broker con permisos de
      escritura en ningún lado del sistema. Esa es la propiedad de seguridad central: la pieza
      que procesa contenido potencialmente hostil (noticias, resultados de búsqueda) es
      estructuralmente incapaz de operar.
- [x] **Automations configuradas (2026-10-11):** `ataraxia-news-sweep` (barrido de noticias,
      L–V 5:45) y `ataraxia-daily-brain` (ciclo de análisis, lun/mié 6:30). Separadas a 45
      minutos a propósito: la contención de sesiones es causa documentada de fallos.
- [ ] Planificar escalabilidad

## 7. Seguridad y Credenciales
- [x] **API keys en `.env`**, fuera de git. `src/config.py` falla con un mensaje claro si
      falta `FMP_API_KEY`, en vez de un 401 confuso más adelante.
- [x] **Scope mínimo en la base de datos:** rol dedicado `ataraxia_brain` vía `psycopg2`, no
      el cliente `supabase-py` (cuyas keys anon/service_role dan acceso total). Verificado en
      vivo que el rol **no puede** hacer `DELETE` ni `CREATE TABLE`. El `CREATE ROLE` con
      password se hace a mano, nunca en una migración versionada — una password committeada
      queda en el historial para siempre.
- [x] **Auditoría de operaciones:** la tabla `decisions` es inmutable por diseño (no se
      hace `UPDATE`, se registra una entrada nueva), y el brain registra toda revisión,
      con acción o sin ella.
- [x] ~~Manejo del flujo de aprobación 2FA diaria~~ — dejó de aplicar: no hay API de broker.

## 8. Testing y Backtesting — Estrategia de Iteración

> ⚠️ **Toda la estrategia de paper trading de esta sección quedó sin efecto el 7-oct.** El
> fondo simulado de $1M se descartó por decisión de LP ("a la basura, ya no nos sirve, era
> solo una prueba de concepto") y Ataraxia pasó a operar sobre la cuenta real de Schwab.
> No hay ambiente de simulación, no hay nocional de paper, y no hay validación previa al
> dinero real: **el capital real está en juego desde el día uno.**
>
> Lo que reemplazó a esta estrategia de iteración: la ejecución manual del usuario como único
> filtro entre la propuesta y el mercado. Es un filtro más débil que una fase de paper —
> protege el capital pero contamina la medición (ver "Problema de atribución" en Sección 1).
> Ese es el trade-off que se aceptó a cambio de no darle a un LLM autoridad sobre dinero real.

- ~~Crear ambiente de simulación~~
- ~~Correr el agente contra datos históricos~~
- ~~**Decidido — todas las iteraciones se corren en paper trading:** la cuenta de paper de
  IBKR es gratuita, ilimitada y usa precios reales, con nocional configurable para que el
  sizing sea representativo~~ — el argumento sigue siendo bueno; lo que desapareció es la
  cuenta de IBKR.
- ~~**Nocional de paper (7-sep-2026): el balance real de la cuenta paper, $1,002,928.12**~~ —
  esa cuenta y sus datos se descartaron.
- ~~Validar resultados antes de usar dinero real~~ — no hay fase previa que validar.

### Criterio de Graduación (paper → capital real) — ⚠️ OBSOLETO, a redefinir

> **Esta sección describe un puente que ya no existe.** Al descartarse el fondo simulado y la
> fase de paper trading (7-oct), Ataraxia opera sobre capital real desde el día uno: no hay
> "graduación" de paper a real. Se conserva el texto porque el **razonamiento sobre qué medir**
> sigue siendo válido y es la mejor base para el criterio nuevo — en particular: que un target
> de outperformance de corto plazo obliga a especular, que el buen razonamiento con retornos
> mediocres es mejor señal que lo inverso, y que una ventana corta es ruido y no señal.
>
> **Pendiente del usuario:** definir qué significa "Ataraxia funciona" sin fase de prueba
> previa — ventana mínima de medición y criterio de muerte del proyecto. La Misión ya fija el
> principio: alpha consistentemente negativo ⇒ liquidar y pasar a indexación pasiva. Falta
> decidir cuánto tiempo es "consistentemente" y qué se hace mientras tanto.

No es un número fijo de semanas ni un target de outperformance tipo "+20-30% vs. S&P". Ese
target no funciona: sobre una ventana corta de paper trading el S&P rinde ~1-2%, así que
pedir 20-30 puntos porcentuales de outperformance obligaría al agente a especular para pasar
el gate — justo lo contrario de la disciplina Carlson que se le pidió. Y la propia
referencia (The Claude Portfolio real) estuvo *por debajo* del S&P en sus primeros días
haciendo todo bien — outperformance de corto plazo es en gran parte ruido, no señal.

En su lugar, graduación = dos gates:
1. **Gate operacional (binario, debe ser 100% limpio):** cero incumplimientos de guardrails
   durante toda la ventana de prueba — sin same-day round-trips, sin posiciones >15%, cada
   operación con rationale + bear case + probabilidad logueados, sin triggers de revisión de
   tesis ignorados, sin fallas de autenticación/API. Esto es lo que el paper trading existe
   para probar (Sección 8 original): bugs y disciplina, no alpha.
2. **Gate de performance, sobre una ventana mínima de un trimestre completo (idealmente dos):**
   no "vencer al benchmark por X%", sino *sin patrón claro de alpha negativo* — retorno
   acumulado en línea o por encima del S&P, y Sharpe ratio no significativamente peor que el
   del benchmark. Alpha positivo real es un bonus, no el mínimo — porque la propia métrica de
   éxito del proyecto (Sección 1) ya dice que el alpha debe ser "sostenido", y un trimestre o
   dos de paper trading es apenas el tamaño de muestra mínimo para que el número signifique algo.

Además, un paso manual: el usuario revisa una muestra de los logs de razonamiento diario y
evalúa si cumplen el estándar "¿lo habría escrito así un buen analista?". Buen razonamiento
con retornos mediocres de corto plazo es mejor señal de graduación que buenos retornos con
razonamiento descuidado — lo segundo suele ser solo suerte disfrazada.

## Investigación Regulatoria (verificado 23 jul 2026, revisado 11 oct 2026)

*La investigación se hizo para IBKR. La cuenta es de Schwab, pero la regla PDT es de FINRA y
aplica a cualquier bróker estadounidense, así que la conclusión no cambia.*

- **Pattern Day Trader (PDT):** regla de FINRA, no de un bróker en particular. En cuentas de
  margen se requieren $25,000 de equity para hacer 4+ day trades en una ventana de 5 días
  hábiles sin restricción.
- **Por qué no es un problema aquí:** estrategia long-only, concentrada, trading solo por
  catalizador (no diario) — no se acerca al umbral de day trading. El guardrail de "sin
  same-day round-trips" lo blinda explícitamente, y con una cuenta de ~$10.4K el umbral de
  $25,000 ni se alcanza.
- **Cash vs. margin:** una cuenta cash no está sujeta a PDT. Ya no es una decisión pendiente:
  la cuenta de Schwab existe y es la que se usa.

## Preguntas Abiertas / Pendientes de Decisión

*Las dos primeras de la lista anterior (tamaño de la primera ronda de capital real, cuenta
cash o margin en IBKR) quedaron sin sentido: no hay IBKR y el capital real ya está en juego.*

- **Criterio de evaluación sin fase de paper:** ventana mínima de medición y criterio de
  muerte del proyecto (ver Sección 8).
- **¿El ciclo de análisis pasa a diario?** Hoy corre lunes y miércoles; el barrido de noticias
  ya es diario. Pasar el ciclo a diario multiplica el costo de modelo por 2.5.
- **¿Qué se hace con el ~33% de la cuenta en ETFs amplios?** Ya está resuelto para la
  *medición* (quedan fuera del alpha), pero no para la *asignación*: si se mantienen como
  ancla conservadora o se reducen para darle espacio a las decisiones de Ataraxia.
- **¿Se conecta la API de Schwab en solo lectura**, o subir los "Lot Details" a mano queda
  como procedimiento permanente?
- **¿ADRs internacionales en el universo?** Hoy excluidos (`solo_listadas_en_eeuu: true`).
- ¿Capa técnica ligera solo para timing de entrada, sí o no? (sección 2)

**Ver también `BUILD_PLAN.md`** para el roadmap técnico de desarrollo (fases, stack, schema
de datos, y el principio de que los guardrails se aplican en código, no se le confían al
criterio del LLM).

## Estado Actual del Proyecto
- **Nombre del agente decidido: Ataraxia**
- **Broker y cuenta (revisado 2026-10-07 — reemplaza la decisión de IBKR):** Ataraxia gestiona
  la **cuenta real de Charles Schwab** del usuario. Ya no hay cuenta separada ni cuenta de
  IBKR. El fondo simulado de $1M se descartó: era prueba de concepto y sus datos de posiciones
  y precios no sirven.
- **Acceso a datos de la cuenta: solo lectura.** Ataraxia ve el portafolio, no lo ejecuta.
  Implementado (11-oct) como **snapshots versionados en Supabase a nivel de lote**: LP sube
  los exports "Lot Details" de Schwab y se cargan con `scripts/load_portfolio_snapshot.py`,
  quedando un registro por fecha de corte en vez de un archivo que se sobreescribe. El aviso
  de antigüedad se conserva (14 días). La ejecución de órdenes la hace el usuario a mano.
  El código de IBKR ya se borró del repo, no solo sus comentarios.
- **Implicación de no tener cuenta separada:** la cartera no parte de cero ni es un lienzo
  limpio. Ataraxia hereda posiciones preexistentes que no eligió, y su trabajo incluye decidir
  qué conservar, qué reducir y qué liquidar. Los guardrails (tope de 15% al costo, revisión de
  tesis a −20%) aplican a las decisiones que Ataraxia toma de aquí en adelante; sobre lo
  heredado funcionan como señal de revisión, no como incumplimiento retroactivo.
- Estrategia definida: long-only, concentrada (**8–15 posiciones**, solo equities), 100%
  análisis fundamental/valuation, con el **framework de Joseph Carlson de tres etapas**
  (riesgo y foso / checklist / valuación) — ROIC > WACC, poder de fijación de precios y el
  caso del atacante son **eliminatorios, no acumulables**.
- **Universo (revisado 2026-10-11):** acciones listadas en EE.UU. con market cap ≥ $2B, sin
  requisito de pertenencia a ningún índice. Pool vigente: 1,681 nombres.
- Cadencia: **barrido de noticias diario (L–V, 5:45) + ciclo de análisis profundo lunes y
  miércoles (6:30)**. Trading solo por catalizador.
- **Iteración (revisado 2026-10-07):** ya no hay fase de paper trading. Al gestionar la cuenta
  real de Schwab desde el inicio, el capital en juego es real y cada recomendación cuenta — la
  validación ocurre sobre dinero real, con ejecución manual del usuario como único filtro
  entre la propuesta de Ataraxia y el mercado.
- **Criterio de graduación: obsoleto, a redefinir** (ver Sección 8). El gate de paper → real
  ya no aplica porque no hay fase de paper.
- Arquitectura: brain = automatización programada de OpenClaw (local, sin LangChain/CrewAI),
  ejecución = **manual (usuario), de forma permanente**. Datos = Financial Modeling Prep (con
  scraping de respaldo donde FMP devuelve 402) + Yahoo Finance como segunda fuente + screener
  de Nasdaq para la lista base del universo + web search nativo.
- **Portafolio versionado en Supabase** (`portfolio_snapshots` + `portfolio_lots`), a nivel de
  lote, con la fecha de compra de cada una. Primer corte cargado: 2026-10-08, 79 lotes en 16
  posiciones, cuenta total $10,397.58.
- **Estado al 2026-10-11: el sistema está operativo.** Próximo paso y riesgos vivos en
  `BUILD_PLAN.md` → "Estado al 2026-10-11 y próximo paso".
