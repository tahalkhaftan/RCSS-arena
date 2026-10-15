"""CI-only native desktop server; never copied into the application image."""
import os,signal
from http.server import ThreadingHTTPServer
from cloud_app import Handler
from native_desktop import DESKTOP
os.environ.update(ARENA_USER='latency-test',ARENA_PASSWORD='latency-test-only')
class CheckHandler(Handler):
 def do_GET(self):
  if self.path=='/native-test/windows':
   if not self.auth():return
   return self.send(200,{'windows':DESKTOP.windows() if DESKTOP.app else []})
  return super().do_GET()
try:
 ThreadingHTTPServer(('0.0.0.0',8000),CheckHandler).serve_forever()
finally:DESKTOP.close()
