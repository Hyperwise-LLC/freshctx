from __future__ import annotations
import asyncio, contextvars, hashlib, inspect, json, math, time, warnings
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import AbstractContextManager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from .adapters import ADAPTERS
from .conformance import normalize_adapter_result
from .errors import AuditFailure, ConfigurationError, FreshCtxError
from .model import ActionEvidenceCorrelation, AdapterResult, CheckResult, FreshnessState, ObservationToken, ReasoningNode, utcnow
from .redaction import redact
from .store import SQLiteStore

_active:contextvars.ContextVar[Any]=contextvars.ContextVar("freshctx_guard",default=None)
DIGEST_DOMAIN = "freshctx.reasoning-digest.v1"
class FreshnessBlocked(FreshCtxError):
    def __init__(self,result,correlation=None):self.result=result;self.correlation=correlation;super().__init__(f"FreshCtx blocked {result.subject_id}: {result.state.value}")

class Guard(AbstractContextManager):
    def __init__(self,policy="block",store=None,run_id=None,audit_path=".freshctx/audit.jsonl",refresh_callback=None,max_graph_depth=100,validation_workers=1,validation_budget_ms=None):
        if policy not in {"block","warn","allow","refresh","replan","require_approval"}:raise ConfigurationError(f"unsupported policy: {policy}")
        if int(validation_workers)<1:raise ConfigurationError("validation_workers must be at least 1")
        if validation_budget_ms is not None and float(validation_budget_ms)<=0:raise ConfigurationError("validation_budget_ms must be positive")
        self.policy=policy;self.store=store or SQLiteStore();self.execution_id=run_id;self.run_id=run_id or str(uuid4());self.audit_path=Path(audit_path);self.refresh_callback=refresh_callback;self.max_graph_depth=max_graph_depth
        self.validation_workers=int(validation_workers);self.validation_budget_ms=None if validation_budget_ms is None else float(validation_budget_ms)
        self.protected=[];self.result=None;self.correlation=None;self._ctx_token=None;self._audit_failed=False
    def __enter__(self):self._ctx_token=_active.set(self);self._audit("guard_started",None,{"policy":self.policy});return self
    def __exit__(self,exc_type,exc,tb):
        try:
            if exc_type is None and self.protected:self.result=self._resolve_policy(self.protected[-1],self.refresh_callback)
        finally:
            if self._ctx_token is not None:_active.reset(self._ctx_token)
        return False
    async def __aenter__(self):
        return self.__enter__()
    async def __aexit__(self,exc_type,exc,tb):
        try:
            if exc_type is None and self.protected:
                self.result=await asyncio.to_thread(self._resolve_policy,self.protected[-1],self.refresh_callback)
        finally:
            if self._ctx_token is not None:_active.reset(self._ctx_token)
        return False
    def _subject(self,value,depends_on,boundary):
        ids=_normalize_dependencies(depends_on)
        if not ids:raise ConfigurationError("depends_on must not be empty")
        if len(ids)==1:return ids[0]
        metadata={"boundary":boundary};node=ReasoningNode("protected_boundary",ids,_reasoning_digest("protected_boundary",ids,metadata),metadata);self.store.put_reasoning(node);return node.id
    def protect(self,value=None,*,depends_on,boundary="output"):
        subject=self._subject(value,depends_on,boundary);self.protected.append(subject);self._audit("protected",subject,{"boundary":boundary});return value
    def run(self,action,*args,depends_on,boundary="action",refresh=None,**kwargs):
        dependency_ids=_normalize_dependencies(depends_on);subject=self._subject(None,dependency_ids,boundary)
        try:result=self._resolve_policy(subject,refresh or self.refresh_callback)
        except FreshnessBlocked as blocked:
            self.result=blocked.result;self.correlation=self._correlate(blocked.result.subject_id,dependency_ids,boundary,action,blocked.result,"blocked")
            raise FreshnessBlocked(blocked.result,self.correlation) from None
        self.result=result
        try:self._audit("action_allowed",result.subject_id,{"action":getattr(action,"__name__",type(action).__name__)},required=self.policy in {"block","refresh","replan","require_approval"})
        except AuditFailure:
            failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed)
        try:self.correlation=self._correlate(result.subject_id,dependency_ids,boundary,action,result,"allowed")
        except AuditFailure:
            self.correlation=None;failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed) from None
        return action(*args,**kwargs)
    async def check_async(self,subject=None):
        """Run synchronous adapter validation without blocking the event loop."""
        return await asyncio.to_thread(self.check,subject)
    async def run_async(self,action,*args,depends_on,boundary="action",refresh=None,**kwargs):
        """Validate, then invoke a synchronous or asynchronous protected action."""
        dependency_ids=_normalize_dependencies(depends_on);subject=self._subject(None,dependency_ids,boundary)
        try:result=await asyncio.to_thread(self._resolve_policy,subject,refresh or self.refresh_callback)
        except FreshnessBlocked as blocked:
            self.result=blocked.result;self.correlation=self._correlate(blocked.result.subject_id,dependency_ids,boundary,action,blocked.result,"blocked")
            raise FreshnessBlocked(blocked.result,self.correlation) from None
        self.result=result
        try:self._audit("action_allowed",result.subject_id,{"action":getattr(action,"__name__",type(action).__name__)},required=self.policy in {"block","refresh","replan","require_approval"})
        except AuditFailure:
            failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed)
        try:self.correlation=self._correlate(result.subject_id,dependency_ids,boundary,action,result,"allowed")
        except AuditFailure:
            self.correlation=None;failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed) from None
        value=action(*args,**kwargs)
        return await value if inspect.isawaitable(value) else value
    def _correlation_graph(self,subject):
        observations=set();reasoning_nodes=set();unresolved=set();integration:dict[str,Any]={};pending=[subject];seen=set()
        while pending:
            object_id=pending.pop()
            if object_id in seen:continue
            seen.add(object_id);obj=self.store.get(object_id)
            if obj is None:unresolved.add(object_id);continue
            if isinstance(obj,ObservationToken):observations.add(obj.id)
            elif isinstance(obj,ReasoningNode):
                reasoning_nodes.add(obj.id);pending.extend(obj.dependencies)
                if obj.metadata.get("contract") and not integration:integration=dict(obj.metadata)
        return tuple(sorted(reasoning_nodes)),tuple(sorted(observations)),tuple(sorted(unresolved)),integration
    def _correlate(self,subject,dependency_ids,boundary,action,result,outcome):
        reasoning_ids,observation_ids,unresolved_ids,integration=self._correlation_graph(subject)
        correlation=ActionEvidenceCorrelation(
            correlation_id=str(uuid4()),run_id=self.run_id,
            runtime=integration.get("runtime"),execution_id=self.execution_id,
            action=str(integration.get("action") or getattr(action,"__name__",type(action).__name__)),
            boundary=boundary,subject_id=subject,declared_dependency_ids=dependency_ids,
            reasoning_ids=reasoning_ids,observation_ids=observation_ids,
            unresolved_dependency_ids=unresolved_ids,freshness_state=result.state,
            policy_decision=result.policy_decision,boundary_outcome=outcome,
            checked_at=result.checked_at,
        )
        if not self._audit_failed:self._audit("action_evidence_correlated",subject,correlation.to_dict(),required=self.policy in {"block","refresh","replan","require_approval"})
        return correlation
    def check(self,subject=None):
        subject_id=_id(subject) if subject is not None else self.protected[-1]
        if self._audit_failed and self.policy in {"block","refresh","replan","require_approval"}:return CheckResult(FreshnessState.UNVERIFIABLE,subject_id,("audit_failure",),(),self._blocked_decision())
        started=time.monotonic()
        if self.validation_workers==1:state,causes,evidence=self._evaluate(subject_id,set(),{},0,started)
        else:state,causes,evidence=self._evaluate_concurrent(subject_id,started)
        decision="allow" if state is FreshnessState.CURRENT or self.policy in {"warn","allow"} else self._blocked_decision()
        result=CheckResult(state,subject_id,tuple(dict.fromkeys(causes)),tuple(evidence),decision)
        details=result.to_dict();details["validation"]={"duration_ms":round((time.monotonic()-started)*1000,3),"workers":self.validation_workers,"budget_ms":self.validation_budget_ms}
        try:self._audit("policy_applied",subject_id,details,required=self.policy in {"block","refresh","replan","require_approval"})
        except AuditFailure:return CheckResult(FreshnessState.UNVERIFIABLE,subject_id,("audit_failure",),tuple(evidence),"block")
        return result
    def _blocked_decision(self):return self.policy if self.policy in {"replan","require_approval"} else "block"
    def _resolve_policy(self,subject,refresh):
        result=self.check(subject)
        if result.state is FreshnessState.CURRENT:return result
        if self.policy=="refresh" and refresh is not None:
            replacement=refresh(result);subject=_id(replacement) if replacement is not None else subject;result=self.check(subject)
            if result.state is FreshnessState.CURRENT:return result
        if self.policy in {"block","refresh","replan","require_approval"}:raise FreshnessBlocked(result)
        if self.policy=="warn":warnings.warn(str(FreshnessBlocked(result)),RuntimeWarning,stacklevel=3)
        return result
    def _budget_exhausted(self,started):return self.validation_budget_ms is not None and (time.monotonic()-started)*1000>=self.validation_budget_ms
    def _validate_observation(self,obj,execution="sequential"):
        strategy=str(obj.metadata.get("freshness_strategy","exact"))
        if strategy=="unverifiable":return AdapterResult("indeterminate",error_code="strategy_unverifiable")
        if strategy=="ttl":
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(obj.observed_at)).total_seconds();maximum=float(obj.metadata["max_age_seconds"])
            except (KeyError,TypeError,ValueError):return AdapterResult("indeterminate",error_code="invalid_ttl_strategy")
            if age>maximum:return AdapterResult("changed",evidence={"reason":"ttl_expired","age_seconds":round(age,6),"max_age_seconds":maximum})
        adapter=ADAPTERS.get(obj.adapter)
        if adapter is None:return AdapterResult("indeterminate",error_code="adapter_missing")
        started=time.monotonic()
        try:result=normalize_adapter_result(adapter.validate(obj))
        except Exception as exc:result=AdapterResult("indeterminate",error_code=type(exc).__name__)
        evidence=dict(result.evidence);evidence.setdefault("duration_ms",round((time.monotonic()-started)*1000,3));evidence.setdefault("freshness_strategy",strategy);evidence.setdefault("validation_execution",execution)
        return replace(result,evidence=evidence)
    @staticmethod
    def _observation_value(obj,ar):
        evidence={"token_id":obj.id,**redact(asdict(ar))}
        if ar.outcome=="equivalent":return FreshnessState.CURRENT,[],[evidence]
        if ar.outcome=="changed":return FreshnessState.STALE_SOURCE,[obj.id],[evidence]
        return FreshnessState.UNVERIFIABLE,[obj.id],[evidence]
    def _evaluate(self,object_id,visiting,memo,depth,started):
        if object_id in memo:return memo[object_id]
        if depth>self.max_graph_depth:return FreshnessState.UNVERIFIABLE,[object_id,"max_graph_depth"],[]
        if object_id in visiting:return FreshnessState.UNVERIFIABLE,[object_id,"cycle"],[]
        obj=self.store.get(object_id)
        if obj is None:return FreshnessState.UNVERIFIABLE,[object_id,"missing_dependency"],[]
        if isinstance(obj,ObservationToken):
            if self._budget_exhausted(started):ar=AdapterResult("indeterminate",error_code="validation_budget_exceeded")
            else:ar=self._validate_observation(obj)
            value=self._observation_value(obj,ar);memo[object_id]=value;return value
        visiting.add(object_id);children=[self._evaluate(dep,visiting,memo,depth+1,started) for dep in obj.dependencies];visiting.remove(object_id)
        evidence=[e for _,_,group in children for e in group];causes=[c for _,group,_ in children for c in group]
        if any(s in {FreshnessState.STALE_SOURCE,FreshnessState.STALE_REASONING} for s,_,_ in children):value=(FreshnessState.STALE_REASONING,causes,evidence)
        elif any(s is FreshnessState.UNVERIFIABLE for s,_,_ in children):value=(FreshnessState.UNVERIFIABLE,causes,evidence)
        else:value=(FreshnessState.CURRENT,[],evidence)
        memo[object_id]=value;return value
    def _evaluate_concurrent(self,subject_id,started):
        objects={};problems={}
        def collect(object_id,visiting,depth):
            if object_id in visiting:problems[object_id]="cycle";return
            if object_id in objects or object_id in problems:return
            if depth>self.max_graph_depth:problems[object_id]="max_graph_depth";return
            obj=self.store.get(object_id)
            if obj is None:problems[object_id]="missing_dependency";return
            objects[object_id]=obj
            if isinstance(obj,ReasoningNode):
                visiting.add(object_id)
                for dependency in obj.dependencies:collect(dependency,visiting,depth+1)
                visiting.remove(object_id)
        collect(subject_id,set(),0)
        observations=[obj for obj in objects.values() if isinstance(obj,ObservationToken)]
        parallel:list[ObservationToken]=[];sequential:list[ObservationToken]=[]
        for obj in observations:
            adapter=ADAPTERS.get(obj.adapter)
            (parallel if adapter is not None and getattr(adapter,"thread_safe",False) else sequential).append(obj)
        executor=ThreadPoolExecutor(max_workers=self.validation_workers,thread_name_prefix="freshctx-validate")
        futures={executor.submit(self._validate_observation,obj,"parallel"):obj for obj in parallel}
        timeout=None if self.validation_budget_ms is None else max(0,(self.validation_budget_ms/1000)-(time.monotonic()-started))
        done,pending=wait(futures,timeout=timeout)
        leaf={obj.id:self._observation_value(obj,future.result()) for future,obj in futures.items() if future in done}
        for future in pending:
            obj=futures[future];leaf[obj.id]=self._observation_value(obj,AdapterResult("indeterminate",evidence={"validation_execution":"parallel","cleanup":"waited_for_started_validator"},error_code="validation_budget_exceeded"))
        # Python cannot safely terminate an arbitrary validator thread. Wait for
        # started validators to reach their adapter-specific timeout so no I/O
        # or custom code survives beyond check(). Their late result is ignored.
        executor.shutdown(wait=True,cancel_futures=True)
        for obj in sequential:
            if self._budget_exhausted(started):
                result=AdapterResult("indeterminate",evidence={"validation_execution":"sequential","started":False},error_code="validation_budget_exceeded")
            else:result=self._validate_observation(obj,"sequential")
            leaf[obj.id]=self._observation_value(obj,result)
        memo:dict[str,tuple[FreshnessState,list[str],list[dict[str,Any]]]]={}
        def aggregate(object_id,visiting,depth):
            if object_id in memo:return memo[object_id]
            if object_id in problems:return FreshnessState.UNVERIFIABLE,[object_id,problems[object_id]],[]
            obj=objects.get(object_id)
            if isinstance(obj,ObservationToken):return leaf[obj.id]
            if obj is None or object_id in visiting or depth>self.max_graph_depth:return FreshnessState.UNVERIFIABLE,[object_id,"cycle" if object_id in visiting else "missing_dependency"],[]
            visiting.add(object_id);children=[aggregate(dep,visiting,depth+1) for dep in obj.dependencies];visiting.remove(object_id)
            evidence=[e for _,_,group in children for e in group];causes=[c for _,group,_ in children for c in group]
            if any(s in {FreshnessState.STALE_SOURCE,FreshnessState.STALE_REASONING} for s,_,_ in children):value=(FreshnessState.STALE_REASONING,causes,evidence)
            elif any(s is FreshnessState.UNVERIFIABLE for s,_,_ in children):value=(FreshnessState.UNVERIFIABLE,causes,evidence)
            else:value=(FreshnessState.CURRENT,[],evidence)
            memo[object_id]=value;return value
        return aggregate(subject_id,set(),0)
    def _audit(self,event_type,subject_id,details,required=False):
        event={"schema_version":1,"event_id":str(uuid4()),"run_id":self.run_id,"event_type":event_type,"timestamp":utcnow(),"subject_id":subject_id,"details":redact(details)}
        try:
            self.audit_path.parent.mkdir(parents=True,exist_ok=True)
            with self.audit_path.open("a",encoding="utf-8") as fh:fh.write(json.dumps(event,sort_keys=True,default=str)+"\n");fh.flush()
        except OSError as exc:
            self._audit_failed=True
            if required:raise AuditFailure("audit sink unavailable") from exc

class ReasoningContext(AbstractContextManager):
    def __init__(self,kind,depends_on,metadata=None):
        raw_metadata=metadata or {};_validate_metadata_keys(raw_metadata)
        self.kind=kind;self.dependencies=_normalize_dependencies(depends_on);self.metadata=_canonical(redact(raw_metadata));self.node=None
    def __enter__(self):return self
    def __exit__(self,exc_type,exc,tb):
        if exc_type is None:
            active=_require_guard();self.node=ReasoningNode(self.kind,self.dependencies,_reasoning_digest(self.kind,self.dependencies,self.metadata),self.metadata);active.store.put_reasoning(self.node)
        return False
    @property
    def id(self):return self.node.id if self.node else None

def guard(policy="block",store=None,run_id=None,audit_path=".freshctx/audit.jsonl",refresh_callback=None,max_graph_depth=100,validation_workers=1,validation_budget_ms=None):return Guard(policy,store,run_id,audit_path,refresh_callback,max_graph_depth,validation_workers,validation_budget_ms)
def observe(locator,adapter=None,**options):
    active=_require_guard();name=adapter or "filesystem"
    if name not in ADAPTERS:raise ConfigurationError(f"unknown adapter: {name}")
    strategy=options.pop("freshness_strategy","exact");max_age=options.pop("max_age_seconds",None)
    if strategy not in {"exact","version","fingerprint","ttl","attestation","unverifiable"}:raise ConfigurationError(f"unsupported freshness_strategy: {strategy}")
    if strategy=="ttl" and (max_age is None or float(max_age)<=0):raise ConfigurationError("ttl strategy requires positive max_age_seconds")
    token=ADAPTERS[name].observe(locator,**options);metadata={**token.metadata,"freshness_strategy":strategy}
    if max_age is not None:metadata["max_age_seconds"]=float(max_age)
    token=replace(token,metadata=metadata);active.store.put_observation(token);active._audit("observed",token.id,{"adapter":name,"locator":token.locator,"freshness_strategy":strategy});return token
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
def _normalize_dependencies(values):return tuple(sorted(set(_id(value) for value in values)))
def _validate_metadata_keys(value):
    if isinstance(value,dict):
        if not all(isinstance(key,str) for key in value):raise ConfigurationError("reasoning metadata keys must be strings")
        for item in value.values():_validate_metadata_keys(item)
    elif isinstance(value,(list,tuple,set,frozenset)):
        for item in value:_validate_metadata_keys(item)
def _canonical(value):
    if isinstance(value,dict):
        if not all(isinstance(key,str) for key in value):raise ConfigurationError("reasoning metadata keys must be strings")
        return {key:_canonical(value[key]) for key in sorted(value)}
    if isinstance(value,(set,frozenset)):
        items=[_canonical(item) for item in value]
        return sorted(items,key=lambda item:json.dumps(item,sort_keys=True,separators=(",",":"),ensure_ascii=False))
    if isinstance(value,(list,tuple)):return [_canonical(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):raise ConfigurationError("reasoning metadata must not contain non-finite numbers")
    if value is None or isinstance(value,(str,int,float,bool)):return value
    raise ConfigurationError(f"unsupported reasoning metadata type: {type(value).__name__}")
def _reasoning_digest(kind,dependencies,metadata):
    payload={"domain":DIGEST_DOMAIN,"kind":str(kind),"dependencies":list(_normalize_dependencies(dependencies)),"metadata":_canonical(metadata)}
    encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
