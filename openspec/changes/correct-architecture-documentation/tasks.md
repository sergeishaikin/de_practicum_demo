# Tasks: correct-architecture-documentation

## Authorised 2026-09-05

- [x] Verify branch, worktree, remotes and local-vs-remote `main` first.
- [x] Establish that the `Airflow` to `Spark Connect` edge has no
      implementation by searching all five DAGs, rather than reasoning from the
      diagram.
- [x] Verify the shipped medallion defaults in both
      `docker-compose.extended.yml` and `.env.example` before rewording the
      medallion description.
- [x] Replace the single architecture graph with six labelled planes, remove
      the false edge, and mark every optional plane with the profile that
      starts it.
- [x] Correct the Iceberg REST, MinIO and Trino relationship in both the
      diagram and the prose.
- [x] Add a *Medallion rollout modes* section with the validated matrix, the
      shipped default, and which metric columns belong to which mode.
- [x] Document all six Compose profiles and state that `otel` and
      `observability-next` are required together.
- [x] Add one sentence to `docs/ARCHITECTURE.md` naming the default rollout
      mode, and confirm the rest of that file was already accurate.
- [x] Sweep `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`,
      `docs/DEVELOPMENT.md` and `docs/DEPLOYMENT.md` for the corrected claims.
- [x] Add the profile-table fitness check and measure its non-vacuity against
      the README on `origin/main`.
- [x] Run the completion gate.
- [ ] Open the pull request against `main`, and record head, base branch, base
      SHA and every required check run id.
- [ ] Archive this change once integrated.

## Explicitly out of scope

- [ ] Changing any shipped default. The `legacy` versus `cutover` question is a
      configuration decision recorded for the backlog, not a documentation fix.
- [ ] Rewriting the `docs/ARCHITECTURE.md` diagrams. Already correct.
- [ ] Fitness checks over descriptive prose.
