@echo off
docker compose exec -T de-demo-postgres psql -U app -d dwh -f /demo_sql/00_layer_snapshot.sql
