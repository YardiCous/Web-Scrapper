# Postgres Setup Guide (WSL and Windows)
```bash
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=listings
DATABASE_URL=postgresql://user:password@localhost:5432/listings
```

---
## Option A: Docker

Requires Docker Desktop with the WSL2 backend and WSL integration enabled for your Ubuntu distro (Settings > Resources > WSL Integration).

```bash
cd ~/project
docker compose up -d db
docker compose ps         
docker compose exec db psql -U USER -d listings -c "\dt"
```

Notes:

- The container reads `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from `.env` and creates them **only the first time**, when the data volume is empty. `init.sql` also runs only then.
- To change credentials or the schema, wipe the volume and start again (**deletes all data**):

```bash
docker compose down -v
docker compose up -d db
```

- Data lives in the `pgdata` Docker volume, not in the project folder.

---

## Option B: Native on Windows

Use this only if you want Postgres to run on Windows itself rather than in WSL.

### 1. Install

Download the installer from postgresql.org (EDB) and run it, or from PowerShell:

```powershell
winget install PostgreSQL.PostgreSQL.16
```

During the installer, you set a password for the built-in `postgres` superuser. Keep the default port **5432** and let it install `psql` and pgAdmin.

### 2. Create the user and database

Open **SQL Shell (psql)** from the Start menu (accept the defaults and enter the `postgres` password), then:

```sql
CREATE USER USER WITH PASSWORD 'PASSWORD';
CREATE DATABASE listings OWNER USER;
\q
```

### 3. Create the tables

From PowerShell in the project folder:

```powershell
psql "postgresql://user:password@localhost:5432/listings" -f db\init.sql
```

If `psql` is not recognized, add `C:\Program Files\PostgreSQL\16\bin` to your PATH.

### 4. Using it from WSL

If the Flask app runs in WSL but Postgres runs on Windows, `localhost` inside WSL may not reach the Windows server. By default Windows Postgres only listens on localhost, so you would need to change `listen_addresses` and `pg_hba.conf` and use the Windows host IP in `DATABASE_URL`. This is fiddly. **Simplest rule: run the app and the database in the same place** (both in WSL, or both on Windows).

---
## Run project
 
Create `.env` using .env.example
 
```bash
cd ~/project/web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Dummy Websites

* https://paegnium.github.io/dummysite/
* https://paegnium.github.io/dummysite2/
* https://paegnium.github.io/dummysite3/


