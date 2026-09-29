import os

# Provide dummy runtime settings so importing application modules does not
# require a real ``conf_dir/.secrets.toml`` during unit tests.
os.environ.setdefault("DYNACONF_DATABASE__HOST", "127.0.0.1")
os.environ.setdefault("DYNACONF_DATABASE__PORT", "5432")
os.environ.setdefault("DYNACONF_DATABASE__USER", "postgres")
os.environ.setdefault("DYNACONF_DATABASE__PASSWORD", "postgres")
os.environ.setdefault("DYNACONF_DATABASE__DBNAME", "postgres")
os.environ.setdefault("DYNACONF_BOTAPI__ENABLE", "false")
