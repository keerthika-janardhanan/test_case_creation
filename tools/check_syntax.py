import py_compile
import sys
path = 'app/run_playwright_recorder.py'
try:
    py_compile.compile(path, doraise=True)
    print('OK')
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
