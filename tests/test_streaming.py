import threading,time,unittest
from runner import LatestProgress
from action_job import RemoteCancel

class Streaming(unittest.TestCase):
 def test_slow_reports_do_not_block_frames_and_keep_latest(self):
  entered=threading.Event();release=threading.Event();seen=[]
  def callback(snapshot):
   seen.append(snapshot['cycle']);entered.set();release.wait(2)
  writer=LatestProgress(callback)
  try:
   writer.submit({'cycle':0});self.assertTrue(entered.wait(1))
   start=time.monotonic()
   for i in range(1,1001):writer.submit({'cycle':i})
   self.assertLess(time.monotonic()-start,.2)
   release.set();writer.close()
   self.assertEqual(seen,[0,1000])
  finally:release.set();writer.close()
 def test_slow_cancel_check_does_not_block_udp_reader(self):
  entered=threading.Event();release=threading.Event()
  class GitHub:
   def assets(self,ident):entered.set();release.wait(2);return {'cancel.json':{}}
  cancel=RemoteCancel(GitHub(),7)
  try:
   start=time.monotonic();self.assertFalse(cancel.is_set());self.assertLess(time.monotonic()-start,.2)
   self.assertTrue(entered.wait(1));release.set()
   deadline=time.monotonic()+1
   while not cancel.is_set() and time.monotonic()<deadline:time.sleep(.005)
   self.assertTrue(cancel.is_set())
  finally:release.set()
