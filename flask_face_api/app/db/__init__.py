from .mysql import init_mysql
from .mongo import init_mongo

try:
    from .redis import init_redis
except ModuleNotFoundError:  # Optional dependency in some local environments.
    def init_redis(app=None):
        return None

