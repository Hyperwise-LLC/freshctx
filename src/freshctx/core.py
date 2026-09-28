from __future__ import annotations
import asyncio, contextvars, hashlib, inspect, json, math, threading, time, warnings
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import AbstractContextManager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from .adapters import ADAPTERS
from .conformance import normalize_adapter_result
from .errors import AuditFailure, ConfigurationError, FreshCtxError, RetryableVerificationError
from .model import ActionAttempt, ActionEvidenceCorrelation, AdapterResult, CheckResult, FreshnessState, ObservationToken, ProtectedParameter, ReasoningNode, RetryPolicy, utcnow
from .redaction import redact
from .store import SQLiteStore

_active:contextvars.ContextVar[Any]=contextvars.ContextVar("freshctx_guard",default=None)
DIGEST_DOMAIN = "freshctx.reasoning-digest.v1"
PARAMETER_DIGEST_DOMAIN = "freshctx.action-parameter.v1"
_PERMANENT_VERIFICATION_ERRORS = frozenset({
    "adapter_missing", "validator_unavailable", "validation_inputs_unavailable",
    "invalid_adapter_result_type", "invalid_adapter_outcome", "invalid_adapter_retry_classification",
    "invalid_ttl_strategy", "strategy_unverifiable", "non_idempotent",
    "validation_budget_exceeded", "FilesystemScopeError", "FilesystemLimitExceeded",
    "ConfigurationError", "StorageCorruptionError", "PermissionError",
    "FileNotFoundError", "ValueError", "TypeError", "http_401", "http_403", "http_404",
})
class FreshnessBlocked(FreshCtxError):
    def __init__(self,result,correlation=None):self.result=result;self.correlation=correlation;super().__init__(f"FreshCtx blocked {result.subject_id}: {result.state.value}")

class Guard(AbstractContextManager):
    def __init__(self,policy="block",store=None,run_id=None,audit_path=".freshctx/audit.jsonl",refresh_callback=None,max_graph_depth=100,validation_workers=1,validation_budget_ms=None,retry_policy=None,action_attempt=None):
        if policy not in {"block","warn","allow","refresh","replan","require_approval"}:raise ConfigurationError(f"unsupported policy: {policy}")
        if int(validation_workers)<1:raise ConfigurationError("validation_workers must be at least 1")
        if validation_budget_ms is not None and (isinstance(validation_budget_ms,bool) or not isinstance(validation_budget_ms,(int,float)) or not math.isfinite(validation_budget_ms) or validation_budget_ms<=0):raise ConfigurationError("validation_budget_ms must be finite and positive")
        self._retry_policy_explicit=retry_policy is not None
        self.retry_policy=retry_policy or RetryPolicy()
        if not isinstance(self.retry_policy,RetryPolicy):raise ConfigurationError("retry_policy must be RetryPolicy")
        rp=self.retry_policy
        if isinstance(rp.max_attempts,bool) or not isinstance(rp.max_attempts,int) or rp.max_attempts<1:raise ConfigurationError("max_attempts must be a positive integer")
        for name,value in (("max_elapsed_ms",rp.max_elapsed_ms),("backoff_ms",rp.backoff_ms)):
            if name=="backoff_ms" and value is None:raise ConfigurationError("backoff_ms must be finite and non-negative")
            if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (value<=0 if name=="max_elapsed_ms" else value<0)):
                raise ConfigurationError(f"{name} must be finite and {'positive' if name=='max_elapsed_ms' else 'non-negative'}")
        if rp.max_attempts>1 and rp.max_elapsed_ms is None and validation_budget_ms is None:raise ConfigurationError("retries require max_elapsed_ms or validation_budget_ms")
        if action_attempt is not None and not isinstance(action_attempt,ActionAttempt):raise ConfigurationError("action_attempt must be ActionAttempt")
        if action_attempt is not None:
            for name in ("operation_id","attempt_id","parent_attempt_id","previous_outcome"):
                value=getattr(action_attempt,name)
                if value is not None and (not isinstance(value,str) or not value.strip()):raise ConfigurationError(f"action_attempt {name} must not be empty")
        self.action_attempt=action_attempt
        self.policy=policy;self.store=store or SQLiteStore();self.execution_id=run_id;self.run_id=run_id or str(uuid4());self.audit_path=Path(audit_path);self.refresh_callback=refresh_callback;self.max_graph_depth=max_graph_depth
        self.validation_workers=int(validation_workers);self.validation_budget_ms=None if validation_budget_ms is None else float(validation_budget_ms)
        self.protected=[];self.result=None;self.correlation=None;self._parameter_nodes={};self._required_lineage=False;self._ctx_token=None;self._audit_failed=False
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
    def run(self,action,*args,depends_on,boundary="action",refresh=None,protected_parameters=None,parameter_values=None,**kwargs):
        dependency_ids=_normalize_dependencies(depends_on);subject,error=self._action_subject(action,args,kwargs,dependency_ids,boundary,protected_parameters,parameter_values)
        if error is not None:
            self.result=error;self.correlation=self._correlate(subject,dependency_ids,boundary,action,error,"blocked")
            raise FreshnessBlocked(error,self.correlation)
        try:result=self._resolve_policy(subject,refresh or self.refresh_callback,require_current=bool(protected_parameters))
        except FreshnessBlocked as blocked:
            self.result=blocked.result;self.correlation=self._correlate(blocked.result.subject_id,dependency_ids,boundary,action,blocked.result,"blocked")
            raise FreshnessBlocked(blocked.result,self.correlation) from None
        self.result=result
        try:self._audit("action_allowed",result.subject_id,{"action":getattr(action,"__name__",type(action).__name__)},required=self._required_lineage or self.policy in {"block","refresh","replan","require_approval"})
        except AuditFailure:
            failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed)
        try:self.correlation=self._correlate(result.subject_id,dependency_ids,boundary,action,result,"allowed")
        except AuditFailure:
            self.correlation=None;failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed) from None
        return action(*args,**kwargs)
    async def check_async(self,subject=None):
        """Run synchronous adapter validation without blocking the event loop."""
        return await asyncio.to_thread(self.check,subject)
    async def run_async(self,action,*args,depends_on,boundary="action",refresh=None,protected_parameters=None,parameter_values=None,**kwargs):
        """Validate, then invoke a synchronous or asynchronous protected action."""
        dependency_ids=_normalize_dependencies(depends_on);subject,error=self._action_subject(action,args,kwargs,dependency_ids,boundary,protected_parameters,parameter_values)
        if error is not None:
            self.result=error;self.correlation=self._correlate(subject,dependency_ids,boundary,action,error,"blocked")
            raise FreshnessBlocked(error,self.correlation)
        try:result=await asyncio.to_thread(self._resolve_policy,subject,refresh or self.refresh_callback,bool(protected_parameters))
        except FreshnessBlocked as blocked:
            self.result=blocked.result;self.correlation=self._correlate(blocked.result.subject_id,dependency_ids,boundary,action,blocked.result,"blocked")
            raise FreshnessBlocked(blocked.result,self.correlation) from None
        self.result=result
        try:self._audit("action_allowed",result.subject_id,{"action":getattr(action,"__name__",type(action).__name__)},required=self._required_lineage or self.policy in {"block","refresh","replan","require_approval"})
        except AuditFailure:
            failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed)
        try:self.correlation=self._correlate(result.subject_id,dependency_ids,boundary,action,result,"allowed")
        except AuditFailure:
            self.correlation=None;failed=CheckResult(FreshnessState.UNVERIFIABLE,subject,("audit_failure",),(),"block");self.result=failed;raise FreshnessBlocked(failed) from None
        value=action(*args,**kwargs)
        return await value if inspect.isawaitable(value) else value
    def _lineage_reaches_observation(self,object_id,visiting,seen,depth):
        if depth>self.max_graph_depth or object_id in visiting:return False
        memo_key=(object_id,depth)
        if memo_key in seen:return seen[memo_key]
        try:obj=self.store.get(object_id)
        except Exception:return False
        if isinstance(obj,ObservationToken):
            valid=(obj.id==object_id and isinstance(obj.metadata,dict) and all(
                isinstance(getattr(obj,key),str) and bool(getattr(obj,key))
                for key in ("id","adapter","locator","fingerprint","validator")
            ))
            seen[memo_key]=valid
            return valid
        if not isinstance(obj,ReasoningNode) or obj.id!=object_id or not obj.dependencies:return False
        try:
            if obj.digest!=_reasoning_digest(obj.kind,obj.dependencies,obj.metadata):return False
        except (TypeError,ValueError,ConfigurationError,AttributeError):return False
        visiting.add(object_id)
        valid=all(self._lineage_reaches_observation(dep,visiting,seen,depth+1) for dep in obj.dependencies)
        visiting.remove(object_id)
        seen[memo_key]=valid
        return valid
    def _action_subject(self,action,args,kwargs,dependency_ids,boundary,protected_parameters,parameter_values):
        self._parameter_nodes={}
        self._required_lineage=bool(protected_parameters)
        if protected_parameters is None:return self._subject(None,dependency_ids,boundary),None
        if not isinstance(protected_parameters,dict):raise ConfigurationError("protected_parameters must map parameter names to ProtectedParameter")
        if not protected_parameters:return self._subject(None,dependency_ids,boundary),None
        binding_failed=False
        try:
            signature=inspect.signature(action)
            bound=signature.bind(*args,**kwargs)
            bound.apply_defaults()
            actual=dict(bound.arguments)
            for name,parameter in signature.parameters.items():
                if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                    actual.update(actual.pop(name,{}))
        except (TypeError,ValueError):actual={};binding_failed=True
        if binding_failed:
            subject=self._subject(None,dependency_ids,boundary) if dependency_ids else str(uuid4())
            return subject,CheckResult(FreshnessState.UNVERIFIABLE,subject,("parameter_binding_unverifiable",),(),"block")
        if parameter_values is not None:
            if not isinstance(parameter_values,dict):raise ConfigurationError("parameter_values must be a mapping")
            for name,value in parameter_values.items():
                try:matches=name not in actual or parameter_digest(actual[name])==parameter_digest(value)
                except (TypeError,ValueError,ConfigurationError,RecursionError):matches=False
                if not matches:
                    subject=self._subject(None,dependency_ids,boundary) if dependency_ids else str(uuid4())
                    return subject,CheckResult(FreshnessState.UNVERIFIABLE,subject,("parameter_value_mismatch",),(),"block")
                actual[name]=value
        roots=list(dependency_ids);lineage_memo:dict[str,bool]={}
        failure=[]
        for name,declared in protected_parameters.items():
            if not isinstance(name,str) or not name or not isinstance(declared,ProtectedParameter):failure.append("invalid_protected_parameter");continue
            try:actual_digest=parameter_digest(actual[name]) if name in actual else None
            except (TypeError,ValueError,ConfigurationError,RecursionError):actual_digest=None
            if not isinstance(declared.value_digest,str) or len(declared.value_digest)!=64 or any(ch not in "0123456789abcdef" for ch in declared.value_digest) or actual_digest!=declared.value_digest:
                failure.append(f"parameter_value_unverifiable:{name}");continue
            try:ids=_normalize_dependencies(declared.dependencies)
            except (TypeError,AttributeError,FreshCtxError):ids=()
            if not ids or not all(self._lineage_reaches_observation(item,set(),lineage_memo,0) for item in ids):
                failure.append(f"parameter_lineage_unverifiable:{name}");continue
            metadata={"parameter":name,"value_digest":declared.value_digest}
            node=ReasoningNode("action_parameter",ids,_reasoning_digest("action_parameter",ids,metadata),metadata)
            self.store.put_reasoning(node);self._parameter_nodes[name]=node.id;roots.append(node.id)
        subject=self._subject(None,tuple(roots),boundary) if roots else str(uuid4())
        if failure:return subject,CheckResult(FreshnessState.UNVERIFIABLE,subject,tuple(failure),(),"block")
        return subject,None
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
            boundary=boundary,subject_id=subject,declared_dependency_ids=tuple(sorted(set(dependency_ids)|set(self._parameter_nodes.values()))) or (subject,),
            reasoning_ids=reasoning_ids,observation_ids=observation_ids,
            unresolved_dependency_ids=unresolved_ids,freshness_state=result.state,
            policy_decision=result.policy_decision,boundary_outcome=outcome,
            operation_id=self.action_attempt.operation_id if self.action_attempt else None,
            attempt_id=self.action_attempt.attempt_id if self.action_attempt else None,
            parent_attempt_id=self.action_attempt.parent_attempt_id if self.action_attempt else None,
            previous_outcome=self.action_attempt.previous_outcome if self.action_attempt else None,
            operation_identity_supplied=bool(self.action_attempt and self.action_attempt.operation_id),
            protected_parameter_ids=dict(self._parameter_nodes),
            attempt_metadata_supplied=self.action_attempt is not None,
            checked_at=result.checked_at,
        )
        if not self._audit_failed:self._audit("action_evidence_correlated",subject,correlation.to_dict(),required=self._required_lineage or self.policy in {"block","refresh","replan","require_approval"})
        return correlation
    def check(self,subject=None,*,require_current=False):
        subject_id=_id(subject) if subject is not None else self.protected[-1]
        if self._audit_failed and (require_current or self.policy in {"block","refresh","replan","require_approval"}):return CheckResult(FreshnessState.UNVERIFIABLE,subject_id,("audit_failure",),(),self._blocked_decision())
        started=time.monotonic()
        if self.validation_workers==1:state,causes,evidence=self._evaluate(subject_id,set(),{},0,started)
        else:state,causes,evidence=self._evaluate_concurrent(subject_id,started)
        decision="allow" if state is FreshnessState.CURRENT or (self.policy in {"warn","allow"} and not require_current) else self._blocked_decision()
        unique_evidence={item.get("token_id",str(index)):item for index,item in enumerate(evidence)}
        result=CheckResult(state,subject_id,tuple(dict.fromkeys(causes)),tuple(unique_evidence.values()),decision)
        details=result.to_dict();details["validation"]={"duration_ms":round((time.monotonic()-started)*1000,3),"workers":self.validation_workers,"budget_ms":self.validation_budget_ms}
        try:self._audit("policy_applied",subject_id,details,required=require_current or self.policy in {"block","refresh","replan","require_approval"})
        except AuditFailure:return CheckResult(FreshnessState.UNVERIFIABLE,subject_id,("audit_failure",),tuple(evidence),"block")
        return result
    def _blocked_decision(self):return self.policy if self.policy in {"replan","require_approval"} else "block"
    def _resolve_policy(self,subject,refresh,require_current=False):
        result=self.check(subject,require_current=require_current)
        if result.state is FreshnessState.CURRENT:return result
        if self.policy=="refresh" and refresh is not None and not require_current:
            replacement=refresh(result);subject=_id(replacement) if replacement is not None else subject;result=self.check(subject)
            if result.state is FreshnessState.CURRENT:return result
        if require_current or self.policy in {"block","refresh","replan","require_approval"}:raise FreshnessBlocked(result)
        if self.policy=="warn":warnings.warn(str(FreshnessBlocked(result)),RuntimeWarning,stacklevel=3)
        return result
    def _budget_exhausted(self,started):return self.validation_budget_ms is not None and (time.monotonic()-started)*1000>=self.validation_budget_ms
    def _validate_observation(self,obj,execution="sequential",check_started=None):
        strategy=str(obj.metadata.get("freshness_strategy","exact"))
        if strategy=="unverifiable":return AdapterResult("indeterminate",error_code="strategy_unverifiable")
        if strategy=="ttl":
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(obj.observed_at)).total_seconds();maximum=float(obj.metadata["max_age_seconds"])
            except (KeyError,TypeError,ValueError):return AdapterResult("indeterminate",error_code="invalid_ttl_strategy")
            if age>maximum:return AdapterResult("changed",evidence={"reason":"ttl_expired","age_seconds":round(age,6),"max_age_seconds":maximum})
        adapter=ADAPTERS.get(obj.adapter)
        if adapter is None:return AdapterResult("indeterminate",error_code="adapter_missing")
        started=time.monotonic();check_started=started if check_started is None else check_started
        policy=self.retry_policy
        hard_deadline=min(
            (check_started+self.validation_budget_ms/1000) if self.validation_budget_ms is not None else math.inf,
            (check_started+policy.max_elapsed_ms/1000) if policy.max_elapsed_ms is not None else math.inf,
        )
        attempts=0
        while True:
            attempts+=1
            if time.monotonic()>=hard_deadline:
                result=AdapterResult("indeterminate",error_code="validation_budget_exceeded")
                break
            if self._retry_policy_explicit and math.isfinite(hard_deadline):
                # A custom validator may ignore its own timeout. Do not start a
                # later verification while that prior call is still running.
                box=[];finished=threading.Event()
                def validate_once():
                    try:box.append(normalize_adapter_result(adapter.validate(obj)))
                    except RetryableVerificationError as exc:box.append(AdapterResult("indeterminate",error_code=type(exc).__name__,retryable=True))
                    except Exception as exc:box.append(AdapterResult("indeterminate",error_code=type(exc).__name__))
                    finally:finished.set()
                threading.Thread(target=validate_once,daemon=True,name="freshctx-evidence-validation").start()
                if not finished.wait(max(0,hard_deadline-time.monotonic())):
                    result=AdapterResult("indeterminate",error_code="validation_budget_exceeded")
                    break
                result=box[0]
            else:
                try:result=normalize_adapter_result(adapter.validate(obj))
                except RetryableVerificationError as exc:result=AdapterResult("indeterminate",error_code=type(exc).__name__,retryable=True)
                except Exception as exc:result=AdapterResult("indeterminate",error_code=type(exc).__name__)
            if time.monotonic()>=hard_deadline:
                result=AdapterResult("indeterminate",error_code="validation_budget_exceeded")
                break
            if result.outcome!="indeterminate" or not result.retryable or result.error_code in _PERMANENT_VERIFICATION_ERRORS or attempts>=policy.max_attempts:
                break
            delay=policy.backoff_ms/1000
            if time.monotonic()+delay>=hard_deadline:
                result=AdapterResult("indeterminate",error_code="validation_budget_exceeded")
                break
            if delay:time.sleep(delay)
        evidence=dict(result.evidence);evidence.setdefault("duration_ms",round((time.monotonic()-started)*1000,3));evidence.setdefault("freshness_strategy",strategy);evidence.setdefault("validation_execution",execution)
        evidence["validation_attempts"]=attempts
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
            else:ar=self._validate_observation(obj,check_started=started)
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
        futures={executor.submit(self._validate_observation,obj,"parallel",started):obj for obj in parallel}
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
            else:result=self._validate_observation(obj,"sequential",started)
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

def guard(policy="block",store=None,run_id=None,audit_path=".freshctx/audit.jsonl",refresh_callback=None,max_graph_depth=100,validation_workers=1,validation_budget_ms=None,retry_policy=None,action_attempt=None):return Guard(policy,store,run_id,audit_path,refresh_callback,max_graph_depth,validation_workers,validation_budget_ms,retry_policy,action_attempt)
def parameter_digest(value):
    """Digest a canonical action value without retaining the value in a record."""
    payload={"domain":PARAMETER_DIGEST_DOMAIN,"value":_parameter_canonical(value)}
    encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
def _parameter_canonical(value):
    if isinstance(value,dict):
        if not all(isinstance(key,str) for key in value):raise ConfigurationError("parameter value object keys must be strings")
        return {key:_parameter_canonical(value[key]) for key in sorted(value)}
    if isinstance(value,list):return [_parameter_canonical(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):raise ConfigurationError("parameter value must be finite")
    if value is None or isinstance(value,(str,int,float,bool)):return value
    raise ConfigurationError(f"unsupported parameter value type: {type(value).__name__}")
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
