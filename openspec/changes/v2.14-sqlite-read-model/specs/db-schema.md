# Spec: SQLite Read Model Schema

## File

`~/.halyard/cache.db`

## Tables

### `sessions`

| Column       | Type    | Notes                                    |
|--------------|---------|------------------------------------------|
| id           | TEXT PK | sha256(raw log line)                     |
| project      | TEXT    | nullable — unattributed sessions have no project |
| tool         | TEXT NN |                                          |
| model        | TEXT NN |                                          |
| started_at   | TEXT NN | ISO 8601 with timezone                   |
| ended_at     | TEXT NN | ISO 8601 with timezone                   |
| input_tok    | INT NN  | default 0                                |
| output_tok   | INT NN  | default 0                                |
| cache_read   | INT     | nullable                                 |
| cache_write  | INT     | nullable                                 |
| cost_usd     | REAL NN | default 0                                |
| tool_calls   | INT     | nullable                                 |
| tool_errors  | INT     | nullable                                 |
| source_file  | TEXT NN | absolute path                            |

### `timeclock`

| Column       | Type        | Notes                   |
|--------------|-------------|-------------------------|
| id           | INT PK AUTO |                         |
| project      | TEXT NN     | client:project slug     |
| started_at   | TEXT NN     |                         |
| ended_at     | TEXT        | NULL = open entry       |
| source_file  | TEXT NN     |                         |

Unique index on `(source_file, started_at, project)`.

### `sync_log`

| Column     | Type        | Notes                  |
|------------|-------------|------------------------|
| id         | INT PK AUTO |                        |
| synced_at  | TEXT NN     | ISO 8601               |
| files_read | INT NN      |                        |
| rows_added | INT NN      |                        |

## Sync behavior

- Sessions are upserted by `id` (sha256 of raw line). Re-running sync is safe.
- Timeclock entries are upserted by `(source_file, started_at, project)`.
- Rows are never deleted from the cache by sync; they persist until
  `halyard db reset` is run.
