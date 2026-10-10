import csv,io,json,os,subprocess,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from dataset import export_dataset
from offline_logs import prepare_team
from runner import run_job
from app import validate

HEADER='ULG5\n(team 0 Blue Orange 0 0)\n(playmode 0 play_on)\n(server_param (player_size 0.3) (kickable_margin 0.7) (ball_size 0.085))\n'
def show(c,count,score=0):
 return f'(show {c} (tm Blue Orange {score} 0) ((b) 0 0 0 0) ((l 7) 0 0x1 0 0 0 0 10 0 (s 7000 1 1 10000) (c {count} 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0x1 10 0 0 0 0 0))\n'
class Dataset(unittest.TestCase):
 def fixture(self,p):
  (p/'match.rcg').write_text(HEADER+''.join(show(c,int(c>1),int(c==51)) for c in range(1,52)))
  (p/'match.rcl').write_text('1,0\tRecv Blue_7: (kick 50 0)(turn_neck 20)\n')
  d=p/'ocl-log/left-team';d.mkdir(parents=True)
  (d/'Blue-7.ocl').write_text('(init l 7 before_kick_off)\n(sense_body 0 (stamina 7000 1 10000))\n(see 1 ((b) 2 0))\n(sense_body 2 (stamina 6900 1 10000))\n')
 def test_join_no_future_input_and_counter_confirmed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);r=export_dataset(p,{},'match',1,2)
   rows=list(csv.DictReader(io.StringIO((p/'decisions.csv').read_text())));row=rows[0]
   self.assertEqual(r['rows'],2);self.assertEqual(row['execution_confirmed'],'1')
   self.assertEqual(row['retained_10c'],'1');self.assertEqual(row['goal_for_within_50c'],'1')
   self.assertEqual(row['ocl_before_cycle'],'0');self.assertNotIn('see 1',row['ocl_messages_before']);self.assertNotIn('6900',row['ocl_messages_before'])
   self.assertEqual(row['gt_l_07_stamina'],'7000.0');self.assertEqual(row['intended_receiver'],'')
   self.assertEqual(rows[1]['execution_confirmed'],'0');self.assertEqual(rows[1]['label_valid'],'0')
   self.assertTrue(r['warnings'])
 def test_repeated_cycles_and_duplicate_commands_never_claim_execution(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p)
   with (p/'match.rcg').open('a') as f:f.write(show(1,0))
   export_dataset(p,{},'m',1,1)
   row=next(csv.DictReader(io.StringIO((p/'decisions.csv').read_text())));self.assertEqual(row['before_state_valid'],'0');self.assertEqual(row['execution_confirmed'],'')
   self.fixture_files_reset(p)
   (p/'match.rcl').write_text('1,0\tRecv Blue_7: (kick 50 0)(kick 40 0)\n')
   export_dataset(p,{},'m',1,1);row=next(csv.DictReader(io.StringIO((p/'decisions.csv').read_text())));self.assertEqual(row['execution_confirmed'],'')
 def fixture_files_reset(self,p):
  (p/'match.rcg').write_text(HEADER+''.join(show(c,int(c>1)) for c in range(1,52)))
 def test_missing_horizon_does_not_become_failure_label(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);(p/'match.rcg').write_text(HEADER+show(1,0)+show(2,1))
   export_dataset(p,{},'m',1,1);row=next(csv.DictReader(io.StringIO((p/'decisions.csv').read_text())))
   self.assertEqual(row['label_valid'],'0');self.assertEqual(row['retained_10c'],'');self.assertEqual(row['goal_for_within_50c'],'')
 def test_private_runtime_wrapper_collects_ocl_without_editing_source(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);src=p/'team';src.mkdir()
   (src/'client.c').write_text(r'''#include <stdio.h>
#include <string.h>
int main(int argc,char **argv){
 if(argc>1&&!strcmp(argv[1],"--help")){puts("--offline_logging --log_dir");return 0;}
 const char *dir=0;int enabled=0;
 for(int i=1;i<argc;i++){if(!strcmp(argv[i],"--offline_logging"))enabled=1;if(!strcmp(argv[i],"--log_dir")&&i+1<argc)dir=argv[++i];}
 if(!enabled||!dir)return 2;
 char name[4096];snprintf(name,sizeof(name),"%s/Blue-7.ocl",dir);
 FILE *f=fopen(name,"w");if(!f)return 3;fputs("(init l 7 before_kick_off)\n(sense_body 0 (stamina 7000 1 10000))\n",f);fclose(f);return 0;}
''')
   subprocess.run(['cc',str(src/'client.c'),'-o',str(src/'player')],check=True)
   before=(src/'player').read_bytes();info=prepare_team(src,p/'runtime',p/'logs',os.environ)
   self.assertEqual(info['supported_clients'],['player'])
   subprocess.run([str(p/'runtime/player')],check=True)
   self.assertTrue((p/'logs/Blue-7.ocl').is_file());self.assertEqual((src/'player').read_bytes(),before)
 def test_zip_contains_per_game_csv_next_to_server_logs(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);state={'id':'123','config':{'offline_logging':True,'rounds':1,'games_per_round':1,'left':{'name':'Blue'},'right':{'name':'Orange'}},'matches':[]}
   job={'state':state,'root':p,'cancel':threading.Event()}
   def fake(config,teams,folder,cancel,progress):
    target=folder/'server-logs';target.mkdir(parents=True);self.fixture(target)
    return {'status':'completed','left_score':1,'right_score':0,'possession':{}}
   def write(_):(p/'results.json').write_text(json.dumps(state))
   with patch('runner.run_match',side_effect=fake):run_job(job,write)
   self.assertEqual(state['status'],'completed');self.assertEqual(state['matches'][0]['dataset']['rows'],2)
   with zipfile.ZipFile(p/'logs.zip') as z:
    root='logs/round-001-game-001/server-logs/'
    for file in ('decisions.csv','match.rcg','match.rcl','ocl-log/left-team/Blue-7.ocl'):self.assertIn(root+file,z.namelist())
 def test_stopped_cycle_messages_do_not_make_unbounded_csv_cells(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p)
   file=p/'ocl-log/left-team/Blue-7.ocl'
   with file.open('a') as out:
    for n in range(1000):out.write('(sense_body 0 (stamina '+str(n)+' 1 10000))\n')
   export_dataset(p,{},'m',1,1)
   row=next(csv.DictReader(io.StringIO((p/'decisions.csv').read_text())))
   self.assertLess(len(row['ocl_messages_before']),1000)
   self.assertIn('999',row['ocl_messages_before'])
 def test_option_type_validation(self):
  c={'rounds':1,'games_per_round':1,'synch_mode':True,'left':{'name':'A','directory':'.','command':'./start.sh'},'right':{'name':'B','directory':'.','command':'./start.sh'},'offline_logging':'true'}
  with self.assertRaises(ValueError):validate(c)
if __name__=='__main__':unittest.main()
