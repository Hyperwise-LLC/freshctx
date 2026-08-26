from __future__ import annotations
import contextvars, hashlib, json, warnings
from contextlib import AbstractContextManager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from .adapters import ADAPTERS
from .model import AdapterResult, CheckResult, FreshnessState, ObservationToken, ReasoningNode, utcnow
from .redaction import redact
from .store import SQLiteStore

_active=contextvars.ContextVar("freshctx_guard",default=None)
class FreshCtxError(RuntimeError):pass
class AuditFailure(FreshCtxError):pass
class ConfigurationError(FreshCtxError):pass
class FreshnessBlocked(FreshCtxError):
    def __init__(self,result):self.result=result;super().__init__(f"FreshCtx blocked {result.subject_id}: {result.state.value}")

class Guard(AbstractContextManager):
    def __init__(self,policy="block",store=None,run_id=None,audit_path=".freshctx/audit.jsonl",refresh_callback=None,max_graph_depth=100):
        if policy not in {"block","warn","allow","refresh"}:raise ConfigurationError(f"unsupported policy: {policy}")
        self.policy=policy;self.store=store or SQLiteStore();self.run_id=run_id or str(uuid4());self.audit_path=Path(audit_path);self.refresh_callback=refresh_callback;self.max_graph_depth=max_graph_depth
        self.protected=[];self.result=None;self._ctx_token=None;self._audit_failed=False
    def __enter__(self):self._ctx_token=_active.set(self);self._audit("guard_started",None,{"policy":self.policy});return self
    def __exit__(self,exc_type,exc,tb):
        try:
            if exc_type is None and self.protected:self.result=self._resolve_policy(self.protected[-1],self.refresh_callback)
        finally:
            if self._ctx_token is not None:_active.reset(self._ctx_token)
        return False
    def _subject(self,value,depends_on,boundary):
        ids=tuple(_id(x) for x in depends_on)
        if not ids:raise ConfigurationError("depends_on must not be empty")
        if len(ids)==1:return ids[0]
        node=ReasoningNode("protected_boundary",ids,_digest(repr(value)),{"boundary":boundary});self.store.put_reasoning(node);return node.id
    def protect(self,value=None,*,depends_on,boundary="output"):
        subject=self._subject(value,depends_on,boundary);self.protected.append(subject);self._audit("protected",subject,{"boundary":boundary});return value
    def run(self,action,*args,depends_on,boundary="action",refresh=None,**kwargs):
        subject=self._subject(None,depends_on,boundary);result=self._resolve_policy(subject,refresh or self.refresh_callback);self.result=result
        try:self._audit("action_allowed",subject,{"action":getattr(action,"__name__",type(action).__name__)},required=self.policy in {"block","refresh"})
        except AuditFailure:
            failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed)
        return action(*args,**kwargs)
    def check(self,subject=None):
        subject_id=_id(subject) if subject is not None else self.protected[-1]
        if self._audit_failed and self.policy in {"block","refresh"}:return CheckResult(FreshnessState.UNVERIFIABLE,subject_id,("audit_failure",),(),"block")
        state,causes,evidence=self._evaluate(subject_id,set(),{},0);decision="allow" if state is FreshnessState.CURRENT or self.policy in {"warn","allow"} else "block"
        result=CheckResult(state,subject_id,tuple(dict.fromkeys(causes)),tuple(evidence),decision)
        try:self._audit("policy_applied",subject_id,result.to_dict(),required=self.policy in {"block","refresh"})
        except AuditFailure:return CheckResult(FreshnessState.UNVERIFIABLE,subject_id,("audit_failure",),tuple(evidence),"block")
        return result
    def _resolve_policy(self,subject,refresh):
        result=self.check(subject)
        if result.state is FreshnessState.CURRENT:return result
        if self.policy=="refresh" and refresh is not None:
            replacement=refresh(result);subject=_id(replacement) if replacement is not None else subject;result=self.check(subject)
            if result.state is FreshnessState.CURRENT:return result
        if self.policy in {"block","refresh"}:raise FreshnessBlocked(result)
        if self.policy=="warn":warnings.warn(str(FreshnessBlocked(result)),RuntimeWarning,stacklevel=3)
        return result
    def _evaluate(self,object_id,visiting,memo,depth):
        if object_id in memo:return memo[object_id]
        if depth>self.max_graph_depth:return FreshnessState.UNVERIFIABLE,[object_id,"max_graph_depth"],[]
        if object_id in visiting:return FreshnessState.UNVERIFIABLE,[object_id,"cycle"],[]
        obj=self.store.get(object_id)
        if obj is None:return FreshnessState.UNVERIFIABLE,[object_id,"missing_dependency"],[]
        if isinstance(obj,ObservationToken):
            adapter=ADAPTERS.get(obj.adapter)
            if adapter is None:return FreshnessState.UNVERIFIABLE,[obj.id,"adapter_missing"],[]
            try:ar=adapter.validate(obj)
            except Exception as exc:ar=AdapterResult("indeterminate",error_code=type(exc).__name__)
            evidence={"token_id":obj.id,**redact(asdict(ar))}
            value=(FreshnessState.CURRENT,[],[evidence]) if ar.outcome=="equivalent" else ((FreshnessState.STALE_SOURCE,[obj.id],[evidence]) if ar.outcome=="changed" else (FreshnessState.UNVERIFIABLE,[obj.id],[evidence]));memo[object_id]=value;return value
        visiting.add(object_id);children=[self._evaluate(dep,visiting,memo,depth+1) for dep in obj.dependencies];visiting.remove(object_id)
        evidence=[e for _,_,group in children for e in group];causes=[c for _,group,_ in children for c in group]
        if any(s in {FreshnessState.STALE_SOURCE,FreshnessState.STALE_REASONING} for s,_,_ in children):value=(FreshnessState.STALE_REASONING,causes,evidence)
        elif any(s is FreshnessState.UNVERIFIABLE for s,_,_ in children):value=(FreshnessState.UNVERIFIABLE,causes,evidence)
        else:value=(FreshnessState.CURRENT,[],evidence)
        memo[object_id]=value;return value
    def _audit(self,event_type,subject_id,details,required=False):
        event={"schema_version":1,"event_id":str(uuid4()),"run_id":self.run_id,"event_type":event_type,"timestamp":utcnow(),"subject_id":subject_id,"details":redact(details)}
        try:
            self.audit_path.parent.mkdir(parents=True,exist_ok=True)
            with self.audit_path.open("a",encoding="utf-8") as fh:fh.write(json.dumps(event,sort_keys=True,default=str)+"\n");fh.flush()
        except OSError as exc:
            self._audit_failed=True
            if required:raise AuditFailure("audit sink unavailable") from exc

class ReasoningContext(AbstractContextManager):
    def __init__(self,kind,depends_on,metadata=None):self.kind=kind;self.dependencies=tuple(_id(x) for x in depends_on);self.metadata=metadata or {};self.node=None
    def __enter__(self):return self
    def __exit__(self,exc_type,exc,tb):
        if exc_type is None:
            active=_require_guard();self.node=ReasoningNode(self.kind,self.dependencies,_digest(self.kind+repr(self.metadata)),redact(self.metadata));active.store.put_reasoning(self.node)
        return False
    @property
    def id(self):return self.node.id if self.node else None

def guard(policy="block",store=None,run_id=None,audit_path=".freshctx/audit.jsonl",refresh_callback=None,max_graph_depth=100):return Guard(policy,store,run_id,audit_path,refresh_callback,max_graph_depth)
def observe(locator,adapter=None,**options):
    active=_require_guard();name=adapter or "filesystem"
    if name not in ADAPTERS:raise ConfigurationError(f"unknown adapter: {name}")
    token=ADAPTERS[name].observe(locator,**options);active.store.put_observation(token);active._audit("observed",token.id,{"adapter":name,"locator":token.locator});return token
def reasoning(kind,depends_on,metadata=None):return ReasoningContext(kind,depends_on,metadata)
def _require_guard():
    value=_active.get()
    if value is None:raise FreshCtxError("FreshCtx operation requires an active guard()")
    return value
def _id(value):
    if isinstance(value,str):return value
    if isinstance(value,ReasoningContext):
        if value.node is None:raise FreshCtxError("reasoning context has not completed")
        return value.node.id
    return value.id
def _digest(value):return hashlib.sha256(value.encode()).hexdigest()
