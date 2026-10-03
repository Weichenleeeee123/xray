/* Durable supplement transport. Browser navigation stops watching, never the server job. */
(function(root,factory){
  if(typeof module==='object'&&module.exports) module.exports=factory();
  else root.SupplementRuns=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function pause(signal){
    return new Promise((resolve,reject)=>{
      const finish=()=>{signal?.removeEventListener('abort',abort);resolve();};
      const abort=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);reject(new Error('已停止查看进度'));};
      const timer=setTimeout(finish,600);
      signal?.addEventListener('abort',abort,{once:true});
      if(signal?.aborted) abort();
    });
  }
  function terminal(message){return Object.assign(new Error(message),{terminal:true});}
  function create({api,storage,randomUUID,wait=pause}){
    const key=id=>'qier.supplement.v1:'+id;
    const memory=new Map();
    function pending(caseId){
      if(memory.has(caseId)) return memory.get(caseId);
      try{
        const record=JSON.parse(storage.getItem(key(caseId))||'null');
        if(record?.caseId===caseId && typeof record.requestKey==='string' && record.body &&
          ['material','reply','need'].includes(record.body.kind) && typeof record.body.text==='string' &&
          (!record.runId || /^[0-9a-f]{24}$/.test(record.runId))) return record;
      }catch(_){}
      return null;
    }
    function save(record){
      try{storage.setItem(key(record.caseId),JSON.stringify(record));}
      catch(_){throw new Error('无法保存任务恢复信息，请允许浏览器本地存储后再试。材料仍保留在当前页面。');}
      memory.set(record.caseId,record);
    }
    function prepare(caseId,body){
      const existing=pending(caseId);
      if(existing) return existing;
      const record={caseId,body:{...body},requestKey:randomUUID()};
      save(record);return record;
    }
    function clear(record){
      if(pending(record.caseId)?.requestKey!==record.requestKey) return;
      try{storage.removeItem(key(record.caseId));}
      catch(_){throw new Error('无法清除任务恢复记录，请允许浏览器本地存储后再试。');}
      memory.delete(record.caseId);
    }
    async function follow(record,{signal,onEvent=()=>{}}={}){
      signal?.throwIfAborted();
      if(!record.runId){
        // A lost response can safely repeat this exact request after a reload.
        let started;
        try {
          started=await api(`/api/cases/${encodeURIComponent(record.caseId)}/runs`,{
            method:'POST',body:record.body,headers:{'Idempotency-Key':record.requestKey},signal,timeoutMs:20000,
          });
        } catch(e) {
          // Validation/access rejection happens before starting a job. 5xx/timeout
          // may have lost the response after creation, so retain the same key.
          if([400,401,403,404,413,422].includes(e.status)) throw terminal(e.message);
          throw e;
        }
        if(!/^[0-9a-f]{24}$/.test(started?.run_id)) throw new Error('任务编号校验不一致');
        record.runId=started.run_id;
        save(record);
      }
      let next=0;
      for(;;){
        signal?.throwIfAborted();
        let page;
        try{page=await api(`/api/runs/${record.runId}?after=${next}`,{signal});}
        catch(e){if(e.status===404)throw terminal('找不到这次任务，请先查看案卷已有版本，确认结果后再重新提交。');throw e;}
        signal?.throwIfAborted();
        if(page.run_id!==record.runId || !Array.isArray(page.events) || !Number.isInteger(page.next) || page.next<next)
          throw new Error('任务进度校验不一致');
        if(page.input && (page.input.kind!=='supplement'||page.input.case_id!==record.caseId))
          throw new Error('任务案卷校验不一致');
        for(const event of page.events){
          if(['begin','step','prebuilt'].includes(event.type)) onEvent(event);
          if(event.type==='error') throw terminal(event.message||'任务生成失败，请检查材料后重新提交。');
        }
        next=page.next;
        if(page.status==='complete'){
          const event=page.events.findLast(e=>e.type==='complete');
          const version=page.version??event?.version;
          if(page.case_id!==record.caseId || (event && (event.case_id!==record.caseId || event.version!==version)) ||
            !Number.isInteger(version)||version<1) throw new Error('任务案卷或版本校验不一致');
          const saved=await api(`/api/cases/${encodeURIComponent(record.caseId)}`,{signal});
          signal?.throwIfAborted();
          if(saved.id!==record.caseId||!saved.versions?.some(v=>v.no===version)) throw new Error('尚未读到任务生成的版本，请恢复进度再确认。');
          return {case:saved,version};
        }
        if(page.status==='error') throw terminal('任务生成失败，请检查材料后重新提交。');
        if(page.status==='interrupted') throw terminal('服务曾中断，任务未确认完成。请先查看案卷已有版本，再决定是否重新提交。');
        if(page.status!=='running') throw new Error('任务状态校验不一致');
        await wait(signal);
      }
    }
    return {pending,prepare,follow,clear};
  }
  return {create};
});
