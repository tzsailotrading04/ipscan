import subprocess as _sp, os as _os
try:
    _sp.run(["apt-get","-qq","update"], capture_output=True, timeout=180)
    _sp.run(["apt-get","-qq","install","-y","masscan"], capture_output=True, timeout=180)
    _v = _sp.run(["masscan","--version"], capture_output=True, text=True, timeout=30)
    print("UID", _os.getuid())
    print("VER", _v.returncode, _v.stdout, _v.stderr)
    _r = _sp.run("timeout 120 masscan 3.0.0.0/20 -p8080,3128,8888,1080,81,8000 --rate 5000", shell=True, capture_output=True, text=True, timeout=150)
    print("SCAN", _r.returncode)
    print(_r.stdout[-3000:])
except Exception as _e:
    print("DIAG", _e)
