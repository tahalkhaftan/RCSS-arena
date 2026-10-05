"""GitHub API used only on the backend/runner. Never expose token to HTML."""
import json
import os
import urllib.request
import urllib.error
from urllib.parse import quote

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result is not None:
            result.remove_header('Authorization')
        return result

class GitHub:
    def __init__(self,repo=None,token=None):
        self.repo=repo or os.environ['GITHUB_REPOSITORY'];self.token=token or os.environ['GITHUB_TOKEN']
        self.base='https://api.github.com/repos/'+self.repo
        self.opener=urllib.request.build_opener(SafeRedirect())
    def require_private(self):
        if self.json('').get('private') is not True:
            raise ValueError('STORAGE_REPOSITORY must be a private GitHub repository')
    def open(self,path,method='GET',body=None,ctype='application/json',binary=False):
        url=path if path.startswith('https://') else self.base+path
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/octet-stream' if binary else 'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'RCSS-Arena','Content-Type':ctype}
        if body is not None and not isinstance(body,bytes): body=json.dumps(body).encode()
        return self.opener.open(urllib.request.Request(url,data=body,method=method,headers=headers),timeout=120)
    def json(self,path,method='GET',body=None):
        with self.open(path,method,body) as r:
            data=r.read();return json.loads(data) if data else None
    def release(self,ident):return self.json('/releases/'+str(int(ident)))
    def assets(self,ident):return {x['name']:x for x in self.json('/releases/'+str(int(ident))+'/assets?per_page=100')}
    def read_asset(self,asset):
        with self.open('/releases/assets/'+str(int(asset['id'])),binary=True) as r:return r.read()
    def put(self,ident,name,content,ctype='application/octet-stream'):
        old=self.assets(ident).get(name)
        if old:self.json('/releases/assets/'+str(old['id']),'DELETE')
        url='https://uploads.github.com/repos/'+self.repo+'/releases/'+str(int(ident))+'/assets?name='+quote(name)
        with self.open(url,'POST',content,ctype) as r:return json.load(r)


def storage_client():
    repo=os.environ.get('STORAGE_REPOSITORY','').strip()
    if not repo:raise ValueError('Configure STORAGE_REPOSITORY (a separate private repository)')
    return GitHub(repo=repo,token=os.environ.get('STORAGE_TOKEN') or os.environ['GITHUB_TOKEN'])
