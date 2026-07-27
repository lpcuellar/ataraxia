# Supabase — despliegue de schema vía GitHub

Este proyecto usa la [integración de GitHub de Supabase](https://supabase.com/docs/guides/deployment/branching/github-integration)
para versionar y desplegar cambios de schema: los archivos en `supabase/migrations/` se
aplican automáticamente a la base de datos real cuando se hace push/merge a `main`.

## Por qué la creación del rol `ataraxia_brain` NO está en una migración

`decisions`, `positions`, `performance`, `universe_state` y los `GRANT` sobre ellas sí viven
en `supabase/migrations/` — no son secretos, y versionarlos es exactamente el punto de esto.

Pero un `CREATE ROLE ... PASSWORD '...'` committeado a Git deja esa password en el historial
para siempre, aunque después se "corrija" en un commit posterior. Por eso ese paso se hace
**una sola vez, a mano**, fuera de Git — ver abajo.

## Setup inicial (una sola vez, en este orden)

1. **Terminar de crear el proyecto en el dashboard de Supabase** (la pantalla de "Create a
   new project"). Usa una password fuerte para la base de datos — esa es la password de
   `postgres`/superusuario, distinta de la del rol `ataraxia_brain`.

2. **Crear el rol `ataraxia_brain` a mano**, en el SQL Editor del dashboard, ANTES de
   conectar GitHub (la migración inicial hace `GRANT ... TO ataraxia_brain`, y eso falla si
   el rol todavía no existe):

   ```sql
   create role ataraxia_brain login password 'PON_AQUI_UNA_PASSWORD_FUERTE_Y_UNICA';
   ```

   Generá la password con un gestor de contraseñas, no la reutilices, y no la pegues en
   ningún archivo de este repo.

3. **Conectar GitHub** (Project Settings → Integrations → Authorize GitHub), eligiendo este
   repositorio. En **Working directory**, poner `.` (el repo tiene como raíz esta misma
   carpeta `ataraxia/`, así que `supabase/` ya está en la raíz del repo).

4. **Activar "Deploy to production"** en la configuración de la integración. Con eso, el
   siguiente push/merge a `main` corre `supabase/migrations/20260726202011_initial_schema.sql`
   contra la base de datos real — que ya va a encontrar el rol `ataraxia_brain` creado en el
   paso 2 y le va a poder hacer los `GRANT`.

5. **Llenar `.env`** con los datos de conexión (`SUPABASE_DB_HOST`, `SUPABASE_DB_PASSWORD` —
   la del rol `ataraxia_brain`, no la de superusuario): el host está en el dashboard, en
   Connect → Session pooler (o Direct connection).

## Cambios futuros al schema

Nuevas migraciones van como archivos nuevos en `supabase/migrations/`, nombrados
`YYYYMMDDHHMMSS_descripcion.sql` (orden cronológico — Supabase los aplica en ese orden).
Nunca editar una migración ya mergeada a `main`: si hay que corregir algo, se agrega una
migración nueva que lo arregla, igual que en cualquier sistema de migraciones de DB.

Recomendación de seguridad: activar el **"required check"** de Supabase en la configuración
de branch protection de GitHub para `main` (Settings → Branches en GitHub), así una
migración inválida no se puede mergear por accidente — Supabase corre un preview/check antes
de permitir el merge.
