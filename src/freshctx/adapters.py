from __future__ import annotations
import hashlib, json, os, subprocess, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit
from .errors import FilesystemLimitExceeded, FilesystemScopeError
from .model import AdapterResult, ObservationToken
from .redaction import redact

def _sha(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def _canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()

class FilesystemAdapter:
    name = "filesystem"
    thread_safe = True
    @staticmethod
    def _within(path:Path,root:Path)->bool:
        try:path.relative_to(root);return True
        except ValueError:return False
    @staticmethod
    def _hash_file(path:Path,max_file_bytes:int)->tuple[str,int]:
        size=path.stat().st_size
        if size>max_file_bytes:raise FilesystemLimitExceeded(f"file exceeds max_file_bytes={max_file_bytes}")
        digest=hashlib.sha256()
        with path.open("rb") as handle:
            read=0
            while chunk:=handle.read(1024*1024):
                read+=len(chunk)
                if read>max_file_bytes:raise FilesystemLimitExceeded(f"file exceeds max_file_bytes={max_file_bytes}")
                digest.update(chunk)
        return digest.hexdigest(),size
    def _fingerprint(self,path:Path,*,root:Path|None,max_file_bytes:int,max_total_bytes:int,max_entries:int,follow_symlinks:bool):
        absolute=path.absolute();is_link=absolute.is_symlink();resolved=absolute.resolve(strict=True)
        boundary=(root.absolute().resolve(strict=True) if root is not None else (absolute.parent.resolve(strict=True) if is_link else (resolved if resolved.is_dir() else resolved.parent)))
        if is_link and not follow_symlinks:
            scoped_path=absolute.parent.resolve(strict=True)/absolute.name
            if not self._within(scoped_path,boundary):raise FilesystemScopeError(f"path is outside root: {boundary}")
            target=os.readlink(absolute);payload=_canonical({"symlink":target})
            return _sha(payload),{"kind":"symlink","size":len(target.encode()),"mtime_ns":absolute.lstat().st_mtime_ns,"resolved_path":str(scoped_path),"root":str(boundary),"max_file_bytes":max_file_bytes,"max_total_bytes":max_total_bytes,"max_entries":max_entries,"follow_symlinks":False}
        if not self._within(resolved,boundary):raise FilesystemScopeError(f"resolved path is outside root: {boundary}")
        stat=resolved.stat();total=0;count=0
        if resolved.is_dir():
            entries:list[tuple[Any,...]]=[]
            for item in sorted(resolved.rglob("*"),key=lambda candidate:str(candidate.relative_to(resolved))):
                count+=1
                if count>max_entries:raise FilesystemLimitExceeded(f"directory exceeds max_entries={max_entries}")
                relative=str(item.relative_to(resolved));item_is_link=item.is_symlink()
                if item_is_link and not follow_symlinks:
                    target=os.readlink(item);entries.append((relative,"symlink",_sha(target.encode())));continue
                item_resolved=item.resolve(strict=True)
                if not self._within(item_resolved,boundary):raise FilesystemScopeError(f"resolved path is outside root: {relative}")
                if item_is_link and item_resolved.is_dir():raise FilesystemScopeError(f"followed directory symlink is unsupported: {relative}")
                if item_resolved.is_file():
                    fingerprint,size=self._hash_file(item_resolved,max_file_bytes);total+=size
                    if total>max_total_bytes:raise FilesystemLimitExceeded(f"directory exceeds max_total_bytes={max_total_bytes}")
                    entries.append((relative,"file",fingerprint,size))
                else:entries.append((relative,"directory"))
            payload=_canonical(entries);kind="directory"
        else:
            fingerprint,total=self._hash_file(resolved,max_file_bytes)
            if total>max_total_bytes:raise FilesystemLimitExceeded(f"source exceeds max_total_bytes={max_total_bytes}")
            payload=fingerprint.encode();kind="file";count=1
        return _sha(payload),{"kind":kind,"size":stat.st_size,"total_bytes":total,"entry_count":count,"mtime_ns":stat.st_mtime_ns,"resolved_path":str(resolved),"root":str(boundary),"max_file_bytes":max_file_bytes,"max_total_bytes":max_total_bytes,"max_entries":max_entries,"follow_symlinks":follow_symlinks}
    def observe(self,locator,*,root=None,max_file_bytes=16*1024*1024,max_total_bytes=64*1024*1024,max_entries=10000,follow_symlinks=False):
        if min(max_file_bytes,max_total_bytes,max_entries)<=0:raise ValueError("filesystem limits must be positive")
        path=Path(locator);fingerprint,metadata=self._fingerprint(path,root=Path(root) if root is not None else None,max_file_bytes=int(max_file_bytes),max_total_bytes=int(max_total_bytes),max_entries=int(max_entries),follow_symlinks=bool(follow_symlinks))
        return ObservationToken(self.name,str(path.absolute()),fingerprint,metadata=metadata)
    def validate(self,token):
        try:fingerprint,metadata=self._fingerprint(Path(token.locator),root=Path(str(token.metadata["root"])),max_file_bytes=int(token.metadata.get("max_file_bytes",16*1024*1024)),max_total_bytes=int(token.metadata.get("max_total_bytes",64*1024*1024)),max_entries=int(token.metadata.get("max_entries",10000)),follow_symlinks=bool(token.metadata.get("follow_symlinks",False)))
        except FileNotFoundError:return AdapterResult("changed",evidence={"reason":"missing"})
        except (FilesystemLimitExceeded,FilesystemScopeError) as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        except OSError as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,**metadata})

class GitAdapter:
    name="git"
    thread_safe=True
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
    thread_safe=True
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
    thread_safe=True
    def __init__(self,connect:Callable|None=None):self.connect=connect;self._dsns:dict[str,str]={};self._validation_inputs:dict[str,tuple[str,Any]]={}
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
        fingerprint,evidence=self._snapshot(dsn,query,params,ordered,timeout);metadata={"dsn_identity":identity,"query_sha256":_sha(query.encode()),"params_sha256":_sha(_canonical(params)),"ordered":ordered,"timeout":timeout,**evidence}
        token=ObservationToken(self.name,identity,fingerprint,metadata=redact(metadata));self._validation_inputs[token.id]=(query,params);return token
    def validate(self,token):
        dsn=self._dsns.get(token.locator);validation=self._validation_inputs.get(token.id)
        if not dsn or validation is None:return AdapterResult("indeterminate",error_code="validation_inputs_unavailable")
        query,params=validation
        try:fingerprint,evidence=self._snapshot(dsn,query,params,bool(token.metadata.get("ordered",True)),float(token.metadata.get("timeout",5)))
        except Exception as exc:return AdapterResult("indeterminate",error_code=type(exc).__name__)
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,**evidence})

class StripeSubscriptionAdapter:
    """Read-only Stripe Subscription freshness adapter.

    API keys and injected transports remain process-local. Tokens contain only
    the subscription ID, selected field names, and non-reversible fingerprints.
    """

    name="stripe_subscription"
    # An application-provided transport may wrap a client that is not safe for
    # concurrent calls. Keep the built-in adapter sequential by default.
    thread_safe=False
    api_base="https://api.stripe.com/v1"
    default_fields=("status","customer","cancel_at_period_end")

    def __init__(self):self._runtime={}
    @staticmethod
    def _field_hashes(snapshot):return {key:_sha(_canonical(value)) for key,value in snapshot.items()}
    @staticmethod
    def _snapshot(payload,subscription_id,fields,include_items):
        if not isinstance(payload,dict) or payload.get("object")!="subscription" or payload.get("id")!=subscription_id:raise ValueError("invalid Stripe Subscription response")
        snapshot={field:payload.get(field) for field in fields}
        if include_items:
            items=payload.get("items",{});data=items.get("data") if isinstance(items,dict) else None
            if not isinstance(data,list):raise ValueError("invalid Stripe Subscription items")
            normalized=[]
            for item in data:
                if not isinstance(item,dict):raise ValueError("invalid Stripe Subscription item")
                price=item.get("price");price_id=price.get("id") if isinstance(price,dict) else price
                normalized.append({"id":item.get("id"),"price":price_id,"quantity":item.get("quantity")})
            snapshot["items"]=sorted(normalized,key=lambda value:str(value.get("id")))
        return snapshot
    def _retrieve(self,subscription_id,api_key,api_version,timeout):
        headers={"Authorization":f"Bearer {api_key}","Accept":"application/json","User-Agent":"freshctx-stripe-subscription/1"}
        if api_version:headers["Stripe-Version"]=api_version
        request=urllib.request.Request(f"{self.api_base}/subscriptions/{quote(subscription_id,safe='')}",headers=headers,method="GET")
        with urllib.request.urlopen(request,timeout=timeout) as response:return json.loads(response.read().decode("utf-8"))
    def observe(self,locator,*,api_key,fields=None,include_items=False,api_version=None,timeout=5.0,transport=None):
        subscription_id=str(locator);fields=tuple(fields or self.default_fields);timeout=float(timeout)
        if not subscription_id.startswith("sub_"):raise ValueError("Stripe subscription ID must start with sub_")
        if not api_key or timeout<=0 or not fields or any(not isinstance(field,str) or not field for field in fields):raise ValueError("Stripe api_key, positive timeout, and fields are required")
        reader=transport or self._retrieve
        payload=reader(subscription_id,str(api_key),api_version,timeout)
        snapshot=self._snapshot(payload,subscription_id,fields,bool(include_items));field_hashes=self._field_hashes(snapshot)
        metadata={"fields":list(fields),"include_items":bool(include_items),"api_version":api_version,"timeout":timeout,"field_hashes":field_hashes}
        token=ObservationToken(self.name,subscription_id,_sha(_canonical(snapshot)),metadata=metadata)
        self._runtime[token.id]=(str(api_key),reader)
        return token
    def validate(self,token):
        runtime=self._runtime.get(token.id)
        if runtime is None:return AdapterResult("indeterminate",error_code="validation_inputs_unavailable")
        api_key,reader=runtime;fields=tuple(token.metadata.get("fields",self.default_fields));include_items=bool(token.metadata.get("include_items",False));timeout=float(token.metadata.get("timeout",5));api_version=token.metadata.get("api_version")
        try:
            payload=reader(token.locator,api_key,api_version,timeout)
            snapshot=self._snapshot(payload,token.locator,fields,include_items)
        except urllib.error.HTTPError as exc:
            if exc.code==404:return AdapterResult("changed",evidence={"reason":"subscription_missing","status":404,"subscription":token.locator})
            return AdapterResult("indeterminate",evidence={"status":exc.code,"subscription":token.locator},error_code=f"stripe_http_{exc.code}")
        except (TimeoutError,urllib.error.URLError,OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
            return AdapterResult("indeterminate",evidence={"subscription":token.locator},error_code="stripe_timeout" if isinstance(exc,TimeoutError) else type(exc).__name__)
        fingerprint=_sha(_canonical(snapshot));current_hashes=self._field_hashes(snapshot);previous=dict(token.metadata.get("field_hashes",{}));changed=sorted(key for key,value in current_hashes.items() if previous.get(key)!=value)
        return AdapterResult("equivalent" if fingerprint==token.fingerprint else "changed",evidence={"fingerprint":fingerprint,"changed_fields":changed,"subscription":token.locator})

class MCPAdapter:
    name="mcp"
    # The application-supplied reader may wrap a session or transport that is
    # not safe for concurrent calls. Keep it sequential unless an application
    # provides a custom adapter with an explicit thread-safety guarantee.
    thread_safe=False
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

ADAPTERS:dict[str,Any]={"filesystem":FilesystemAdapter(),"git":GitAdapter(),"http":HTTPAdapter(),"postgres":PostgresAdapter(),"stripe_subscription":StripeSubscriptionAdapter(),"mcp":MCPAdapter()}
def register_adapter(name,adapter):ADAPTERS[name]=adapter
