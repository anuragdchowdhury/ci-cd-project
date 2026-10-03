"""Container integration check: the release image migrates an empty DB and exits."""
import subprocess


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, **kwargs)

run("docker", "compose", "exec", "-T", "db", "sh", "-ec",
    'createdb -U "$POSTGRES_USER" migration_smoke')
run("docker", "compose", "run", "--rm", "--no-deps",
    "-e", "DB_URL=jdbc:postgresql://db:5432/migration_smoke",
    "-e", "APP_MIGRATE_ONLY=true", "-e", "SPRING_MAIN_WEB_APPLICATION_TYPE=none",
    "-e", "SPRING_FLYWAY_ENABLED=true", "-e", "SPRING_JPA_HIBERNATE_DDL_AUTO=none",
    "backend", timeout=180)
result = subprocess.check_output([
    "docker", "compose", "exec", "-T", "db", "sh", "-ec",
    'psql -U "$POSTGRES_USER" -d migration_smoke -Atc "SELECT count(*) FROM flyway_schema_history WHERE success; SELECT count(*) FROM notes;"'
], text=True)
if result.strip().splitlines() != ["1", "0"]:
    raise SystemExit("Migration did not create an empty notes table and successful history")
print("PASS: same backend image completed the migration Job and exited.")
