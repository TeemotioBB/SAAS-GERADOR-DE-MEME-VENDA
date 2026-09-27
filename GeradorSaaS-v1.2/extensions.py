from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def rate_limit_key():
    try:
        if current_user.is_authenticated:
            return f"user:{current_user.get_id()}"
    except Exception:
        pass
    return f"ip:{get_remote_address()}"


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=rate_limit_key, default_limits=[])
