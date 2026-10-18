"""Build pinned server and isolated team APIs once, without site/team secrets."""
import ast,json,os,subprocess,tarfile
from pathlib import Path


def library_versions(source):
    tree=ast.parse(Path(source).read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LIBRARIES' for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError('Pinned LIBRARIES are missing')


def main():
    work=Path('/tmp/arena-image-build');sources=Path('/opt/arena-sources');sources.mkdir(parents=True,exist_ok=True)
    def run(command,cwd=work,env=None):
        print('$ '+' '.join(map(str,command)),flush=True)
        subprocess.run(list(map(str,command)),cwd=cwd,env=env,check=True)
    run(['cmake','-S',work/'server','-B',work/'server-build','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX=/opt/arena-server','-DCMAKE_INSTALL_LIBDIR=lib'])
    run(['cmake','--build',work/'server-build','--parallel','4'])
    run(['cmake','--install',work/'server-build'])
    manifest={}
    for base,(repo,revision) in library_versions('/opt/arena-runtime/team_build.py').items():
        source=work/base;source.mkdir()
        run(['git','init',source]);run(['git','fetch','--depth','1','https://github.com/'+repo+'.git',revision],source)
        run(['git','checkout','--detach','FETCH_HEAD'],source)
        home=Path('/opt/arena-libs')/base;home.mkdir(parents=True,exist_ok=True)
        prefix=home/'local'/'starter' if base=='school' else home
        env=os.environ.copy();env['HOME']=str(home)
        if base=='school':
            run(['cmake','-S',source,'-B',work/'school-build','-DCMAKE_INSTALL_LIBDIR=lib'],env=env)
            run(['cmake','--build',work/'school-build','--parallel','4'],env=env)
            run(['cmake','--install',work/'school-build'],env=env)
        else:
            run(['./bootstrap'],source,env)
            run(['./configure','--disable-unit-test','--prefix='+str(prefix)],source,env)
            run(['make','-j','4'],source,env);run(['make','install'],source,env)
        if not (prefix/'include'/'rcsc'/'types.h').is_file() or not list((prefix/'lib').glob('librcsc*.so*')):
            raise RuntimeError('Matching headers/shared libraries missing: '+base)
        manifest[base]={'repository':repo,'revision':revision,'prefix':str(prefix)}
        # Distribute corresponding source alongside the compiled GPL libraries.
        with tarfile.open(sources/(base+'-librcsc.tar.gz'),'w:gz') as archive:
            archive.add(source,arcname=base+'-librcsc',filter=lambda info:None if '/.git/' in info.name or info.name.endswith('/.git') else info)
    Path('/opt/arena-libs/manifest.json').write_text(json.dumps(manifest,indent=2))
    print('READY: RCSSServer 19.0.0 + isolated school/university libraries',flush=True)

if __name__=='__main__':main()
