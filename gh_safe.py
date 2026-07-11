import os,json,time,urllib.request,urllib.error
API="https://api.github.com"; REPO=os.environ.get("AETHER_REPO","globalsuplementsofficial-lang/aether-offload")
def _h():
    t=os.environ.get("AETHER_PAT") or os.environ.get("GH_OFFLOAD_PAT") or ""
    return {"Authorization":"Bearer "+t,"User-Agent":"aether","Accept":"application/vnd.github+json","Content-Type":"application/json"}
def call(m,p,b=None,_r=0):
    r=urllib.request.Request(API+p,method=m,headers=_h())
    if b is not None: r.data=json.dumps(b).encode()
    try:
        x=urllib.request.urlopen(r,timeout=40); rem=x.headers.get("x-ratelimit-remaining")
        if rem is not None and int(rem)<100:
            reset=int(x.headers.get("x-ratelimit-reset",time.time()+60)); time.sleep(min(max(0,reset-int(time.time()))+2,120))
        return x.status,json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        ra=e.headers.get("Retry-After")
        if e.code in (403,429) and _r<4: time.sleep(int(ra) if ra else min(2**_r*15,120)); return call(m,p,b,_r+1)
        return e.code,e.read().decode()[:200]
def commit_many(files,message):
    _,ref=call("GET","/repos/%s/git/ref/heads/main"%REPO); base=ref["object"]["sha"]
    _,cm=call("GET","/repos/%s/git/commits/%s"%(REPO,base))
    tree=[{"path":p,"mode":"100644","type":"blob","content":cc} for p,cc in files.items()]
    _,tr=call("POST","/repos/%s/git/trees"%REPO,{"base_tree":cm["tree"]["sha"],"tree":tree})
    _,nc=call("POST","/repos/%s/git/commits"%REPO,{"message":message,"tree":tr["sha"],"parents":[base]})
    return call("PATCH","/repos/%s/git/refs/heads/main"%REPO,{"sha":nc["sha"]})
