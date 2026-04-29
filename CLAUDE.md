# storytelling-bot — notes for Claude Code

## Shell command conventions

- Для psql используй `psql -f path/to/query.sql` или heredoc (`psql <<'EOF' ... EOF`), а не `psql -c "многострочный SQL с -- комментариями"`. Многострочный quoted SQL триггерит security-предупреждение Claude Code про `\n#` в кавычках.
- Не объединяй команды через `cd ... && cmd`. Лучше передавай рабочую директорию параметром инструмента или используй абсолютные пути — это позволяет узкому allowlist срабатывать без `Bash(cd:*)`.
- Не передавай пароли в URL (`postgresql://user:pass@...`). Используй `~/.pgpass` или переменную `PGPASSWORD`.
