import io,json,os,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from app import validate
from runner import run_job
from team_build import build_team,source_root,BuildCancelled

class TeamBuild(unittest.TestCase):
    def project(self,root,fail=False):
        p=Path(root)/'wrapped'/'Team';p.mkdir(parents=True)
        (p/'bootstrap').write_text('#!/bin/sh\necho BOOTSTRAP\n')
        (p/'configure').write_text('#!/bin/sh\necho CONFIGURE\n'+('echo specific-compiler-error >&2\nexit 7\n' if fail else ''))
        (p/'hello.c').write_text('int main(void){return 0;}\n')
        (p/'Makefile').write_text('all:\n\tmkdir -p src\n\tcc hello.c -o src/player\n\tprintf \'#!/bin/sh\\n./player\\n\' > src/start.sh\n\tchmod +x src/start.sh\n')
        return p

    def test_university_compiles_real_c_and_uses_src(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.project(root)
            team={'base':'university','source_directory':'','command':'./custom.sh'};log=root/'build.log'
            stages=[];result=build_team(team,root,log,threading.Event(),stages.append)
            self.assertEqual(stages,['./bootstrap','./configure','make -j 8'])
            self.assertEqual(team['directory'],'wrapped/Team/src');self.assertEqual(team['command'],'./custom.sh')
            self.assertTrue((root/team['directory']/'player').is_file());self.assertEqual(result['directory'],team['directory'])

    def test_school_build_directory_and_command_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.project(root);tool=root/'tools';tool.mkdir()
            # CMake shim generates a real Makefile; compilation is still performed by the real make/cc.
            cmake=tool/'cmake';cmake.write_text('#!/bin/sh\ncat > Makefile <<\'EOF\'\nall:\n\tmkdir -p bin\n\tcc ../hello.c -o bin/player\n\tprintf \'#!/bin/sh\\n./player\\n\' > bin/start.sh\n\tchmod +x bin/start.sh\nEOF\n');cmake.chmod(0o700)
            stages=[];team={'base':'school'}
            with patch.dict(os.environ,{'PATH':str(tool)+':'+os.environ['PATH']}):build_team(team,root,root/'log',threading.Event(),stages.append)
            self.assertEqual(stages,['./bootstrap','./configure','mkdir -p build','cmake ..','make -j 8'])
            self.assertTrue((root/team['directory']/'player').is_file());self.assertEqual(team['directory'],'wrapped/Team/build/bin')

    def test_failure_keeps_full_terminal_and_does_not_run_matches(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.project(root/'teams'/'left',True)
            config={'left':{'input_mode':'source','base':'university','name':'A','directory':'.','command':'./start.sh'},'right':{'name':'B','directory':'bin','command':'./start.sh'},'rounds':1,'games_per_round':3}
            state={'config':config,'matches':[]};job={'state':state,'root':root,'cancel':threading.Event()}
            def write(_):(root/'results.json').write_text(json.dumps(state))
            with patch('runner.run_match') as match:run_job(job,write);match.assert_not_called()
            self.assertEqual(state['status'],'failed');self.assertEqual(state['builds']['left']['status'],'failed')
            self.assertIn('specific-compiler-error',state['builds']['left']['log_tail'])
            with zipfile.ZipFile(root/'logs.zip') as archive:self.assertIn('specific-compiler-error',archive.read('logs/build-left.log').decode())

    def test_two_matches_build_source_only_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state={'config':{'left':{'input_mode':'source','base':'school','name':'A','directory':'.','command':'./mine.sh'},'right':{'name':'B','directory':'bin','command':'./start.sh'},'rounds':1,'games_per_round':2},'matches':[]}
            def write(_):(root/'results.json').write_text(json.dumps(state))
            def built(team,*args):team['directory']='Team/build/bin';return {'directory':team['directory']}
            with patch('runner.build_team',side_effect=built) as builder,patch('runner.run_match',return_value={'status':'completed','left_score':0,'right_score':0}):
                run_job({'state':state,'root':root,'cancel':threading.Event()},write)
            self.assertEqual(builder.call_count,1);self.assertEqual(len(state['matches']),2)

    def test_ambiguous_root_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.project(root/'one');self.project(root/'two')
            with self.assertRaisesRegex(ValueError,'expected one'):source_root(root)
            with self.assertRaises(ValueError):source_root(root,'../outside')

    def test_cancel_build_does_not_start_script(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.project(root);cancel=threading.Event();cancel.set()
            with self.assertRaises(BuildCancelled):build_team({'base':'university'},root,root/'log',cancel)

    def test_source_validation_and_binary_backwards_compatibility(self):
        base={'rounds':1,'games_per_round':1,'synch_mode':False,'left':{'name':'A','directory':'bin','command':'./start.sh'},'right':{'name':'B','directory':'bin','command':'./start.sh'}}
        self.assertEqual(validate(base)['left']['input_mode'],'binary')
        base['left'].update(input_mode='source',base='school',source_directory='../escape')
        with self.assertRaises(ValueError):validate(base)
