"""Web Dashboard auth."""
import os as _os, functools
from flask import request, jsonify

DASHBOARD_TOKEN=_os.environ.get("DASHBOARD_TOKEN","")
AUTH_ENABLED=bool(DASHBOARD_TOKEN)

def require_auth(view_func):
    @functools.wraps(view_func)
    def wrapper(*a,**kw):
        if not AUTH_ENABLED: return view_func(*a,**kw)
        token=request.headers.get("X-Dashboard-Token","") or request.args.get("token","")
        if token!=DASHBOARD_TOKEN: return jsonify({"error":"Unauthorized"}),401
        return view_func(*a,**kw)
    return wrapper

def auth_status():
    return {"auth_enabled":AUTH_ENABLED,"method":"token" if AUTH_ENABLED else "none"}
