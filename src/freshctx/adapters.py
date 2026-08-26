from __future__ import annotations
import hashlib, json, os, subprocess, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from .model import AdapterResult, ObservationToken
from .redaction import redact

def _sha(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def _canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()

class FilesystemAdapter:
    name = "filesystem"
    @staticmethod
    def _fingerprint(path: Path):
        resolved=path.resolve(strict=True); stat=resolved.stat()
        if resolved.is_dir():
            entries=[]
            for item in sorted(resolved.rglob("*"),key=lambda p:str(p.relative_to(resolved))):
                entries.append((str(item.relative_to(resolved)),_sha(item.read_bytes()) if item.is_file() else "dir"))
            payload=_canonical(entries); kind="directory"
        else: payload=resolved.read_bytes(); kind="file"
        return _sha(payload),{"kind":kind,"size":stat.st_size,"mtime_ns":stat.st_mtime_ns}
    def observe(self,locator):
        path=Path(locator); fingerprint,metadata=self._fingerprint(path)
        return ObservationToken(self.name,str(path.resolve()),fingerprint,metadata=metadata)
    def validate(self,token):
        try:fingerprint,metadata=self._fingerprint(Path(token.locator))
        except FileNotFoundError:return AdapterResult("changed",evidence={"reason":"missing"})
        except OSError as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,**metadata})

class GitAdapter:
    name="git"
    @staticmethod
    def _run(repo,*args):return subprocess.run(["git","-C",str(repo),*args],check=True,capture_output=True,text=True,timeout=5).stdout.strip()
    def _snapshot(self,repo,scope,path,ref):
        root=Path(self._run(repo,"rev-parse","--show-toplevel")).resolve(); commit=self._run(root,"rev-parse",ref)
        if scope=="path":
            if not path:raise ValueError("Git path scope requires path=")
            normalized=str(Path(path).as_posix()).lstrip("/"); object_id=self._run(root,"rev-parse",f"{ref}:{normalized}"); dirty=self._run(root,"status","--porcelain=v1","--",normalized)
            payload={"scope":scope,"path":normalized,"object_id":object_id,"dirty":dirty}
        elif scope=="repository":
            dirty=self._run(root,"status","--porcelain=v1","--untracked-files=all"); payload={"scope":scope,"commit":commit,"dirty":dirty}
        else:raise ValueError("Git scope must be 'repository' or 'path'")
        return _sha(_canonical(payload)),{"repo":str(root),"ref":ref,"commit":commit,**payload}
    def observe(self,locator,*,scope="repository",path=None,ref="HEAD"):
        fingerprint,metadata=self._snapshot(Path(locator),scope,path,ref); return ObservationToken(self.name,metadata["repo"],fingerprint,metadata=metadata)
    def validate(self,token):
        try:fingerprint,metadata=self._snapshot(Path(token.locator),str(token.metadata.get("scope","repository")),token.metadata.get("path"),str(token.metadata.get("ref","HEAD")))
        except subprocess.TimeoutExpired:return AdapterResult("indeterminate",error_code="git_timeout")
        except (subprocess.CalledProcessError,FileNotFoundError,OSError,ValueError) as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        safe={k:v for k,v in metadata.items() if k!="dirty"}; safe["dirty"]=bool(metadata.get("dirty"))
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,**safe})

class HTTPAdapter:
    name="http"
    def __init__(self):self._runtime_headers={}
    @staticmethod
    def _safe_url(url):
        p=urlsplit(url); host=p.hostname or ""; host=f"{host}:{p.port}" if p.port else host
        return redact(urlunsplit((p.scheme,host,p.path,p.query,p.fragment)))
    def _request(self,url,headers,timeout):
        req=urllib.request.Request(url,headers=headers,method="GET"); start=time.monotonic()
        try:
            response=urllib.request.urlopen(req,timeout=timeout); body=response.read(); status=response.status; final=response.geturl(); rh=dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            if exc.code==304:return 304,b"",url,dict(exc.headers.items()),int((time.monotonic()-start)*1000)
            raise
        return status,body,final,rh,int((time.monotonic()-start)*1000)
    def observe(self,locator,*,headers=None,timeout=5.0):
        headers=dict(headers or {}); status,body,final,rh,_=self._request(str(locator),headers,timeout)
        metadata={"status":status,"etag":rh.get("ETag"),"last_modified":rh.get("Last-Modified"),"body_sha256":_sha(body),"final_url":self._safe_url(final),"timeout":timeout}
        token=ObservationToken(self.name,self._safe_url(str(locator)),_sha(_canonical(metadata)),metadata=metadata); self._runtime_headers[token.id]=headers; return token
    def validate(self,token):
        headers=dict(self._runtime_headers.get(token.id,{})); etag=token.metadata.get("etag"); modified=token.metadata.get("last_modified")
        if etag:headers["If-None-Match"]=str(etag)
        elif modified:headers["If-Modified-Since"]=str(modified)
        try:status,body,final,rh,latency=self._request(token.locator,headers,float(token.metadata.get("timeout",5)))
        except (TimeoutError,urllib.error.URLError,OSError,ValueError) as exc:return AdapterResult("indeterminate",evidence={"url":token.locator},error_code="http_timeout" if isinstance(exc,TimeoutError) else type(exc).__name__)
        if status==304:return AdapterResult("equivalent",evidence={"status":304,"latency_ms":latency,"url":token.locator})
        body_hash=_sha(body); old_etag=str(etag or ""); new_etag=str(rh.get("ETag") or "")
        equivalent=(old_etag==new_etag) if old_etag and new_etag and not old_etag.startswith("W/") and not new_etag.startswith("W/") else body_hash==token.metadata.get("body_sha256") and status==token.metadata.get("status")
        return AdapterResult("equivalent" if equivalent else "changed",evidence={"status":status,"etag":new_etag or None,"body_sha256":body_hash,"latency_ms":latency,"url":self._safe_url(final)})

class PostgresAdapter:
    name="postgres"
    def __init__(self,connect:Callable|None=None):self.connect=connect;self._dsns={}
    def _connector(self):
        if self.connect:return self.connect
        try:
            import psycopg
            return psycopg.connect
        except ImportError as exc:raise RuntimeError("install freshctx[postgres]") from exc
    @staticmethod
    def _rows(cursor,ordered):
        columns=[d[0] if isinstance(d,(tuple,list)) else d.name for d in (cursor.description or [])]; encoded=[dict(zip(columns,row)) for row in cursor.fetchall()]
        return encoded if ordered else sorted(encoded,key=_canonical)
    def _snapshot(self,dsn,query,params,ordered,timeout):
        conn=self._connector()(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY");cur.execute(f"SET LOCAL statement_timeout = {int(timeout*1000)}");cur.execute(query,params);rows=self._rows(cur,ordered)
            return _sha(_canonical(rows)),{"row_count":len(rows),"ordered":ordered}
        finally:conn.close()
    def observe(self,locator,*,query,params=None,ordered=True,timeout=5.0):
        dsn=str(locator);identity=_sha(dsn.encode());self._dsns[identity]=dsn;params=params or []
        fingerprint,evidence=self._snapshot(dsn,query,params,ordered,timeout);metadata={"dsn_identity":identity,"query_sha256":_sha(query.encode()),"query":query,"params_sha256":_sha(_canonical(params)),"params":params,"ordered":ordered,"timeout":timeout,**evidence}
        return ObservationToken(self.name,identity,fingerprint,metadata=redact(metadata))
    def validate(self,token):
        dsn=self._dsns.get(token.locator)
        if not dsn:return AdapterResult("indeterminate",error_code="credentials_unavailable")
        try:fingerprint,evidence=self._snapshot(dsn,token.metadata["query"],token.metadata.get("params",[]),bool(token.metadata.get("ordered",True)),float(token.metadata.get("timeout",5)))
        except Exception as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,**evidence})

class MCPAdapter:
    name="mcp"
    def __init__(self):self._validators={}
    def observe(self,locator,*,name,arguments=None,reader=None,safe=True,version=None):
        arguments=arguments or {};key=_sha(_canonical([locator,name,arguments]));metadata={"server":str(locator),"name":name,"arguments":redact(arguments),"arguments_sha256":_sha(_canonical(arguments)),"safe":safe,"version":version,"validator_key":key}
        if not safe or reader is None:return ObservationToken(self.name,str(locator),"unverifiable",metadata=metadata)
        value=reader();self._validators[key]=reader;return ObservationToken(self.name,str(locator),_sha(_canonical(value)),metadata=metadata)
    def validate(self,token):
        if not token.metadata.get("safe"):return AdapterResult("indeterminate",error_code="non_idempotent")
        reader=self._validators.get(str(token.metadata.get("validator_key")))
        if reader is None:return AdapterResult("indeterminate",error_code="validator_unavailable")
        try:fingerprint=_sha(_canonical(reader()))
        except Exception as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,"server":token.locator,"name":token.metadata.get("name")})

ADAPTERS={"filesystem":FilesystemAdapter(),"git":GitAdapter(),"http":HTTPAdapter(),"postgres":PostgresAdapter(),"mcp":MCPAdapter()}
def register_adapter(name,adapter):ADAPTERS[name]=adapter
