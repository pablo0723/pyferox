# Configuration

PyFerOx uses typed settings via `load_config()` from `pyferox.config`.

## Load Config

```python
from pyferox.config import load_config

config = load_config()
```

`load_config` returns `AppConfig`:

- `profile`
- `app_name`
- `database` (`DatabaseConfig`)
- `http` (`HttpConfig`)
- `modules` (module-specific settings map)
- `secret_key`

## Environment Files

Load order:

1. `.env` (if `load_dotenv=True`)
2. profile resolution (`PYFEROX_PROFILE` or explicit profile arg)
3. `.env.<profile>` loaded with override enabled

This allows profile-specific overrides.

## Main Environment Variables

Default prefix is `PYFEROX_`.

- `PYFEROX_PROFILE`: `dev`, `test`, `prod`
- `PYFEROX_APP_NAME`: app name string
- `PYFEROX_DB_URL`: SQLAlchemy URL
- `PYFEROX_DB_ECHO`: boolean (`1/0`, `true/false`, `yes/no`, `on/off`)
- `PYFEROX_HTTP_HOST`: host string
- `PYFEROX_HTTP_PORT`: integer
- `PYFEROX_HTTP_DEBUG`: boolean
- `PYFEROX_SECRET_KEY`: optional secret

Profile overrides:

- `test`: forces `http.debug=True`
- `prod`: forces `db.echo=False` and `http.debug=False`

## Module-Level Settings

Format:

`<PREFIX>MODULE_<MODULE_NAME>__<SETTING_NAME>=<value>`

Example:

```bash
PYFEROX_MODULE_USERS__MAX_PAGE_SIZE=250
PYFEROX_MODULE_USERS__ENABLED=true
PYFEROX_MODULE_BILLING__TAX_RATE=0.2
```

Values are parsed as:

- boolean when matching known boolean tokens
- int when possible
- float when possible
- string otherwise

Read:

```python
users_cfg = config.modules["users"].values
max_page_size = users_cfg["max_page_size"]  # 250
```

## Secret Providers

Built-in providers:

- `EnvSecretProvider`
- `DictSecretProvider`
- `FileSecretProvider`
- `ChainedSecretProvider`

Example:

```python
from pathlib import Path
from pyferox.config import ChainedSecretProvider, DictSecretProvider, FileSecretProvider, load_config

provider = ChainedSecretProvider(
    DictSecretProvider({"PYFEROX_SECRET_KEY": "dev-secret"}),
    FileSecretProvider(Path("/run/secrets")),
)
config = load_config(secret_provider=provider)
```

## CLI Config Inspection

```bash
pyferox inspect-config
pyferox inspect-config --profile prod
```

This prints resolved config as JSON.
