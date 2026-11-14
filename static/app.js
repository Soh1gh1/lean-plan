'use strict';

const paths = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2m4 0h2m-8 3h2"/>',
  chart:'<path d="M4 3v17h17M8 14l4-5 4 3 5-7"/>',
  settings:'<path d="m9 3-.7 2.3-2 .9L4 5.7 2.5 8.3 4.2 10v2L2.5 14 4 16.6l2.3-.5 2 .9L9 20h6l.7-3 2-.9 2.3.5 1.5-2.6-1.7-2v-2l1.7-1.7L20 5.7l-2.3.5-2-.9L15 3z"/><circle cx="12" cy="11.5" r="3"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  weight:'<rect x="4" y="4" width="16" height="17" rx="4"/><path d="M8 8a6 6 0 0 1 8 0l-2 5h-4zM12 7v3"/>',
  flame:'<path d="M13 3c1 5-5 6-3 10 1-2 3-2 3-4 4 3 6 5 6 8a7 7 0 0 1-14 0c0-5 6-6 8-14Z"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  down:'<path d="M5 7l5 5 4-4 5 9M14 17h5v-5"/>',
  up:'<path d="m5 17 5-5 4 4 5-9m-5 0h5v5"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 3v4m-2-2h4"/>',
  edit:'<path d="m15 5 4 4M4 20l5-1 12-12a2.8 2.8 0 0 0-4-4L5 15z"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  back:'<path d="m15 5-7 7 7 7"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload:'<path d="M12 15V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  steps:'<path d="M8 3c-3 1-4 6-3 9 .8 2 4 1 4-1L9 5c0-1 0-2-1-2Zm-3 13c-2 3 2 6 4 3l1-2ZM16 5c3 1 4 6 3 9-.8 2-4 1-4-1l0-6c0-1 0-2 1-2Zm3 13c2 3-2 6-4 3l-1-2Z"/>',
  activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  leaf:'<path d="M20 3c0 12-3 17-10 17a7 7 0 0 1-6-7C4 5 14 6 20 3ZM4 21l11-10"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  archive:'<path d="M4 8v12h16V8M3 3h18v5H3zM9 12h6"/>',
};
const icon = (name, extra='') => `<svg class="icon ${extra}" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.info}</svg>`;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(value,digits=0)=>value==null?'No data':Number(value).toLocaleString('en-GB',{minimumFractionDigits:digits,maximumFractionDigits:digits});
const dateObj=value=>new Date(`${value}T12:00:00`);
const dateText=(value,options={day:'numeric',month:'short'})=>dateObj(value).toLocaleDateString('en-GB',options);
const shiftDate=(value,days)=>{const d=dateObj(value);d.setDate(d.getDate()+days);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const dayCount=value=>`${value} ${value===1?'day':'days'}`;
const apart=(a,b)=>Math.round((dateObj(b)-dateObj(a))/86400000);
const sum=values=>{let total=0,correction=0;for(const value of values){const next=total+value;correction+=Math.abs(total)>=Math.abs(value)?(total-next)+value:(value-next)+total;total=next;}return total+correction;};
const average=values=>values.length?sum(values)/values.length:null;
const round=value=>{if(value==null)return null;const scaled=Math.abs(value)*1000;return (Math.sign(value)*Math.floor(scaled+.5+4*Number.EPSILON*Math.max(1,scaled))/1000)||0;};
const isPresent=value=>value!==null&&value!==undefined;
const content=document.querySelector('#content'),modalRoot=document.querySelector('#modal-root');
const dailyKeys=['weight','protein','fat','carbs','calorie_override','training_minutes','training_met','steps','steps_kcal','note'];
let base,state,page='overview',chartRange=30,journalPage=0,archiveView=null,modalArchive=null,archiveLoadSequence=0,modalDate=null,modalKind='',wizardStep=0,previousFocus,insightKind='weight',dayTab='measurements';
let sequence=0,baseVersion=0,pumpPromise=null,saveTimer=null,retryTimer=null,toastTimer=null;
const drafts=new Map();

async function api(path,payload){
  const response=await fetch(path,payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Leanplan-Token':base.token},body:JSON.stringify(payload),keepalive:true});
  const result=await response.json();
  if(!response.ok){const error=new Error(result.error||'Could not save.');error.status=response.status;throw error;}
  return result;
}
function nutrition(row){
  const macros=['protein','fat','carbs'].some(key=>isPresent(row[key])),manual=isPresent(row.calorie_override);
  const calculated=macros?round((row.protein??0)*4+(row.fat??0)*9+(row.carbs??0)*4):null;
  return {calories:manual?round(row.calorie_override):calculated,calculated_calories:calculated,calories_source:manual?'manual':macros?'macros':null,tef:macros?round((row.protein??0)*1+(row.carbs??0)*.3+(row.fat??0)*.18):null};
}
function hasData(row){return ['weight','protein','fat','carbs','calorie_override','training_minutes','steps','steps_kcal'].some(key=>isPresent(row[key]))||!!row.note;}
const isManualCalories=row=>row?.calories_source==='manual'||isPresent(row?.calorie_override);
function calculate(row,settings,weight,weightDate){
  const n=nutrition(row);
  let bmr=weight!=null&&settings.age!=null&&settings.age>=18&&settings.height!=null&&['male','female'].includes(settings.sex)?10*weight+6.25*settings.height-5*settings.age+(settings.sex==='male'?5:-161):null;
  if(bmr!==null&&bmr<=0)bmr=null;
  const met=row.training_met??2.25;
  const training=isPresent(row.training_minutes)&&weight!=null?row.training_minutes*(met-1)*3.5*weight/200:row.training_minutes===0?0:null;
  const expenditure=bmr===null?null:bmr+sum([training,row.steps_kcal,n.tef].filter(isPresent));
  return {...row,...n,effective_weight:weight,weight_source_date:weightDate,bmr:round(bmr),bmr_formula:'mifflin_st_jeor',training_kcal:round(training),training_met_used:met,tdee:round(expenditure),deficit:round(expenditure!=null&&n.calories!=null?expenditure-n.calories:null),has_data:hasData(row)};
}
function rebuild(){
  const settings={...base.settings},rows=new Map(base.entries.map(row=>[row.date,{...row}]));
  for(const [key,job] of drafts){
    const patch=Object.fromEntries(Object.entries(job.fields).map(([field,record])=>[field,record.value]));
    if(key==='settings'){
      Object.assign(settings,patch);
      if(Object.hasOwn(patch,'training_met')&&rows.has(base.today))rows.set(base.today,{...rows.get(base.today),training_met:patch.training_met??2.25});
    }
    else{
      const day=key.slice(6),existing=rows.get(day)||Object.fromEntries(dailyKeys.map(field=>[field,field==='note'?'':null]));
      const met=Object.hasOwn(patch,'training_met')?(patch.training_met??settings.training_met):(existing.training_met??settings.training_met);
      rows.set(day,{...existing,...patch,date:day,entered_late:existing.entered_late||day<base.today,first_recorded_on:existing.first_recorded_on||base.today,training_met:met});
    }
  }
  let weight=base.baseline?.weight??null,weightDate=base.baseline?.date??null;
  const entries=[...rows.values()].filter(row=>row.date<=base.today).sort((a,b)=>a.date.localeCompare(b.date)).map(row=>{
    if(row.weight!=null){weight=row.weight;weightDate=row.date;}
    return calculate(row,settings,weight,weightDate);
  });
  const weights=entries.filter(row=>row.weight!=null),calories=entries.map(row=>row.calories).filter(isPresent),balances=entries.map(row=>row.deficit).filter(isPresent);
  for(const row of entries){const sample=weights.filter(w=>w.date>=shiftDate(row.date,-6)&&w.date<=row.date);row.weight_average=round(average(sample.map(w=>w.weight)));row.weight_average_samples=sample.length;}
  const recent=weights.filter(row=>row.date>=shiftDate(base.today,-6)).map(row=>row.weight),previous=weights.filter(row=>row.date>=shiftDate(base.today,-13)&&row.date<shiftDate(base.today,-6)).map(row=>row.weight);
  const start=base.baseline?.weight??weights[0]?.weight??null,latest=weights.at(-1)?.weight??base.baseline?.weight??null,goal=settings.goal_weight;
  let goalProgress=null;if(start!=null&&goal!=null)goalProgress=start===goal?(latest===goal?100:0):Math.max(0,Math.min(100,100*(latest-start)/(goal-start)));
  const today=entries.find(row=>row.date===base.today)||calculate({date:base.today},settings,weight,weightDate);
  state={...base,settings,entries,today_stats:today,summary:{...base.summary,entry_count:entries.filter(row=>row.has_data).length,weight_count:weights.length,latest_weight:latest,latest_weight_date:weights.at(-1)?.date??base.baseline?.date??null,start_weight:start,start_date:base.baseline?.date??weights[0]?.date??null,weight_change:weights.length&&(weights.length>1||base.baseline?.weight!=null)?round(latest-start):null,average_calories:round(average(calories)),calorie_count:calories.length,total_deficit:balances.length?round(sum(balances)):null,deficit_days:balances.length,recent_average:round(average(recent)),previous_average:round(average(previous)),recent_samples:recent.length,previous_samples:previous.length,trend_change:recent.length&&previous.length?round(average(recent)-average(previous)):null,goal_progress:round(goalProgress)}};
}
function status(){
  window.leanplanPending=drafts.size>0||pumpPromise!==null;
  const error=[...drafts.values()].find(job=>job.error)?.error;
  const el=document.querySelector('#sync-status');
  el.dataset.state=error?'error':window.leanplanPending?'pending':'saved';
  el.querySelector('span:last-child').textContent=error?'Not saved · retrying':window.leanplanPending?'Saving…':'Saved on device';
  el.title=error||'';
}
function stage(kind,day,field,value){
  stageFields(kind,day,{[field]:value});
}
function stageFields(kind,day,fields){
  const key=kind==='settings'?'settings':`entry:${day}`;
  const job=drafts.get(key)||{fields:{},error:null};
  for(const [field,value] of Object.entries(fields))job.fields[field]={value,revision:++sequence};
  job.error=null;drafts.set(key,job);
  rebuild();refreshPanels();status();
  clearTimeout(saveTimer);clearTimeout(retryTimer);saveTimer=setTimeout(()=>flushAll().catch(()=>{}),120);
}
async function flushAll(){
  clearTimeout(saveTimer);
  if(pumpPromise)return pumpPromise;
  if(!drafts.size)return;
  pumpPromise=(async()=>{
    while(drafts.size){
      const [key,job]=drafts.entries().next().value;
      const snapshot={...job.fields},values=Object.fromEntries(Object.entries(snapshot).map(([field,record])=>[field,record.value]));
      try{
        const result=await api(key==='settings'?'/api/settings':'/api/entry',key==='settings'?values:{date:key.slice(6),...values});
        base=result;baseVersion++;
        for(const [field,record] of Object.entries(snapshot))if(job.fields[field]?.revision===record.revision)delete job.fields[field];
        if(!Object.keys(job.fields).length)drafts.delete(key);
        rebuild();refreshPanels();
      }catch(error){
        job.error=error.message||'Connection interrupted.';status();
        if(!error.status||error.status>=500){clearTimeout(retryTimer);retryTimer=setTimeout(()=>flushAll().catch(()=>{}),1500);}
        throw error;
      }
    }
  })();
  status();
  try{await pumpPromise;}finally{pumpPromise=null;status();}
}
window.flushAll=flushAll;
function toast(message){const el=document.querySelector('#toast');clearTimeout(toastTimer);el.textContent=message;el.classList.add('visible');toastTimer=setTimeout(()=>el.classList.remove('visible'),3000);}
function metric(label,value,unit='',caption='',tone='',help=''){
  const empty=value==='No data';
  const size=String(value).length<=7?26:String(value).length<=10?20:String(value).length<=12?16:14;
  return `<article class="metric ${empty?'is-empty':''}" ${help?`title="${esc(help)}"`:''}><span>${label}</span><strong class="${tone}" style="--metric-size:${size}px" title="${esc(value)}${empty?'':` ${esc(unit)}`}">${value}${!empty&&unit?`<small>${unit}</small>`:''}</strong>${caption&&!empty?`<small>${caption}</small>`:''}</article>`;
}
function balanceMetric(label,value,caption=''){
  return metric(label,fmt(value==null?null:Math.abs(value)),'kcal',value==null?'':`${value>0?'Deficit':value<0?'Surplus':'Balanced'}${caption?` · ${caption}`:''}`,value==null?'':value>=0?'green':'rose');
}
function summaryMarkup(insights=false){
  const s=state.summary,t=state.today_stats;
  if(insights)return metric('Latest weight',fmt(s.latest_weight,1),'kg',s.latest_weight_date?dateText(s.latest_weight_date):'')+metric('Weight change',s.weight_change==null?'No data':`${s.weight_change>0?'+':''}${fmt(s.weight_change,1)}`,'kg')+metric('Average intake',fmt(s.average_calories),'kcal')+metric('Weekly change',s.trend_change==null?'No data':`${s.trend_change>0?'+':''}${fmt(s.trend_change,2)}`,'kg','7-day averages')+metric('Recorded days',fmt(s.entry_count),s.entry_count===1?'day':'days')+balanceMetric('Period balance',s.total_deficit,dayCount(s.deficit_days));
  const help=t.bmr==null?'Needs weight, age, height and a selected sex coefficient.':'Estimated resting energy: Mifflin–St Jeor uses weight, height, age and sex.';
  return metric('BMR',fmt(t.bmr),'kcal','Mifflin–St Jeor','',help)+metric('Avg calories',fmt(s.average_calories),'kcal')+metric('Est. expenditure',fmt(t.tdee),'kcal','','','Resting energy + estimated TEF + net training + entered active walking kcal. Unlogged activity is not included.')+balanceMetric('Today',t.deficit)+balanceMetric('Period balance',s.total_deficit,dayCount(s.deficit_days));
}
function field(label,name,value,{unit='',type='number',min='',max='',id='',placeholder='',options=null,kind='',day='',help=''}={}){
  const fieldId=id||`${kind||'field'}-${name}`;
  const attrs=`name="${name}" id="${fieldId}" aria-label="${esc(label)}" ${help?`title="${esc(help)}"`:''} ${kind?`data-kind="${kind}"`:''} ${day?`data-date="${day}"`:''}`;
  const control=options?`<select ${attrs}>${options.map(([v,text])=>`<option value="${v}" ${v===value?'selected':''}>${text}</option>`).join('')}</select>`:type==='textarea'?`<textarea ${attrs} rows="2" maxlength="2000" placeholder="${esc(placeholder)}">${esc(value)}</textarea>`:`<input ${attrs} type="${type}" value="${esc(value??'')}" placeholder="${esc(placeholder)}" ${type==='number'?`min="${min}" max="${max}" step="${['age','steps'].includes(name)?'1':'any'}" inputmode="decimal"`:''} ${type==='text'?'maxlength="60"':''}>`;
  return `<label class="field" for="${fieldId}"><span>${label}</span><div class="input-wrap">${control}${unit?`<small>${unit}</small>`:''}</div></label>`;
}

function nutritionMarkup(day){const row=state.entries.find(entry=>entry.date===day)||{};const n=nutrition(row);return derivedMarkup('Calories',n.calories,0,isManualCalories(row)?'manual-value':'')+derivedMarkup('TEF',n.tef,1);}
function ranges(){return `<div class="segmented" role="group" aria-label="Chart range">${[[7,'7D'],[30,'30D'],[90,'90D'],[0,'All']].map(([days,label])=>`<button data-action="range" data-days="${days}" class="${chartRange===days?'active':''}" aria-pressed="${chartRange===days}">${label}</button>`).join('')}</div>`;}
function chartMarkup(kind='weight',compact=false){
  const data=state.entries.filter(row=>(!chartRange||row.date>=shiftDate(state.today,-chartRange+1))&&row[kind]!=null);
  if(!data.length)return `<div class="chart-empty">${icon(kind==='weight'?'chart':'flame')}<span>${kind==='weight'?'No measurements':'No calorie records'}</span></div>`;
  const W=912,H=compact?176:256,L=42,R=17,T=17,B=30,iw=W-L-R,ih=H-T-B;
  let start=kind==='weight'?data[0].date:chartRange?shiftDate(state.today,-chartRange+1):data[0].date;
  const end=kind==='weight'?data.at(-1).date:state.today;
  if(kind!=='weight'&&start===end)start=shiftDate(start,-1);
  const span=apart(start,end),values=data.map(row=>row[kind]);
  const low=kind==='weight'?Math.floor((Math.min(...values)-.6)*2)/2:0;
  const high=kind==='weight'?Math.ceil((Math.max(...values)+.6)*2)/2:Math.max(500,Math.ceil(Math.max(...values)*1.1/500)*500);
  const x=day=>span?L+apart(start,day)/span*iw:L+iw/2,y=value=>T+(high-value)/(high-low||1)*ih;
  let result=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${kind==='weight'?'Weight history':'Calculated calorie history'}"><defs><linearGradient id="area-${kind}" x1="0" y1="0" x2="0" y2="1"><stop class="chart-stop" stop-opacity=".18"/><stop class="chart-stop" offset="100%" stop-opacity="0"/></linearGradient></defs>`;
  for(let i=0;i<=4;i++){const value=low+(high-low)*i/4;result+=`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${y(value)}" y2="${y(value)}"/><text class="chart-label" x="${L-10}" y="${y(value)+4}" text-anchor="end">${fmt(value,kind==='weight'?1:0)}</text>`;}
  let ticks;
  if(kind==='weight'){
    ticks=[start];
    for(const row of data.slice(1,-1))if(x(row.date)-x(ticks.at(-1))>=iw/4&&x(end)-x(row.date)>=100)ticks.push(row.date);
    if(end!==start)ticks.push(end);
  }else ticks=Array.from({length:5},(_,i)=>shiftDate(start,Math.round(span*i/4)));
  ticks.forEach((day,i)=>{result+=`<text class="chart-label" data-chart-tick="${day}" x="${x(day)}" y="${H-6}" text-anchor="${ticks.length===1?'middle':i===0?'start':i===ticks.length-1?'end':'middle'}">${dateText(day)}</text>`;});
  if(kind==='weight'){
    if(data.length>1){const line=data.map(row=>`${x(row.date)},${y(row.weight)}`).join(' ');result+=`<polygon fill="url(#area-weight)" points="${x(data[0].date)},${H-B} ${line} ${x(data.at(-1).date)},${H-B}"/><polyline class="weight-line" points="${line}"/><polyline class="mean-line" points="${data.map(row=>`${x(row.date)},${y(row.weight_average)}`).join(' ')}"/>`;}
    for(const row of data)result+=`<circle class="chart-dot ${row.entered_late?'late-dot':''}" cx="${x(row.date)}" cy="${y(row.weight)}" r="3.7"/><circle class="chart-hit" cx="${x(row.date)}" cy="${y(row.weight)}" r="13" tabindex="0" data-chart-date="${row.date}" data-chart-kind="weight"><title>${dateText(row.date)} · ${fmt(row.weight,1)} kg${row.entered_late?' · Late entry':''}</title></circle>`;
  }else{
    const width=Math.max(2,Math.min(23,iw/(span+1)*.65));
    for(const row of data)result+=`<rect class="calorie-bar ${row.entered_late?'late-bar':''} ${isManualCalories(row)?'manual-bar':''}" x="${x(row.date)-width/2}" y="${y(row.calories)}" width="${width}" height="${Math.max(2,H-B-y(row.calories))}" rx="3"/><rect class="chart-hit" x="${x(row.date)-Math.max(8,width/2)}" y="${T}" width="${Math.max(16,width)}" height="${ih}" tabindex="0" data-chart-date="${row.date}" data-chart-kind="calories"><title>${dateText(row.date)} · ${fmt(row.calories)} kcal${isManualCalories(row)?' · Manual':''}${row.entered_late?' · Late entry':''}</title></rect>`;
  }
  return result+'</svg>';
}

function header(title){return `<header class="page-header" data-layout="page-header"><h1>${title}</h1><time>${dateText(state.today,{day:'numeric',month:'long',year:'numeric'})}</time></header>`;}
function dayStatus(row,day){if(row?.entered_late)return '<span class="badge late-badge">Late entry</span>';if(day===state.today)return '<span class="badge today-badge">Today</span>';return row?.has_data?'<span class="recorded-dot" title="Recorded"></span>':'<span class="missing-label">Missing</span>';}



function renderOverview(){
  content.innerHTML=header('Overview')+`<section class="page-body overview-body" data-layout="page-body"><section class="metrics" id="overview-metrics">${weightMetricMarkup()}<div id="overview-readouts">${summaryMarkup()}</div></section><section class="nutrition-section"><div class="section-head"><h2>Calories</h2></div>${overviewEditorMarkup()}</section><section class="activity-section"><div class="section-head"><h2>Activity</h2></div>${overviewActivityMarkup()}</section><section class="chart-section compact-chart" data-layout="chart"><div class="section-head"><h2>Weight</h2>${ranges()}</div><div id="weight-plot" class="chart-wrap">${chartMarkup('weight',true)}</div><div class="chart-legend"><span><i></i>Weight</span><span><i class="mean"></i>7-day mean</span></div></section></section>`;
}

const journalData=()=>archiveView||state;
const dayData=()=>modalArchive||state;
const JOURNAL_PAGE_SIZE=8;
function journalDays(){const source=journalData(),end=source.end_date||source.today,count=Math.max(1,apart(source.journal_start,end)+1);return {source,end,count,pages:Math.ceil(count/JOURNAL_PAGE_SIZE)};}
function periodOptions(){return `<option value="current">Current period</option>`+(state.archives||[]).map(a=>`<option value="${a.id}" ${archiveView?.id===a.id?'selected':''}>${esc(a.name)} · ${dateText(a.start_date)} – ${dateText(a.end_date)}</option>`).join('');}
function renderHistory(){
  content.innerHTML=header('Daily journal')+`<section class="page-body journal-body" data-layout="page-body"><div class="section-head journal-head"><select id="journal-period" aria-label="Journal period">${periodOptions()}</select><div class="journal-actions"><button class="button subtle" data-action="archive-period" title="Archive completed days through yesterday. Today stays in the current period." ${archiveView||!state.entries.some(r=>r.date<state.today&&r.has_data)?'disabled':''}>${icon('archive')}Archive period</button><button class="button subtle" data-action="export" data-format="csv">${icon('download')}CSV</button><button class="icon-button danger" data-action="clear-history" aria-label="Clear history" title="Clear all history">${icon('trash')}</button></div></div><div class="journal-summary" id="journal-summary">${journalSummaryMarkup()}</div><div class="journal-table" id="journal-table">${journalListMarkup()}</div><div class="journal-footer" id="journal-footer">${journalFooterMarkup()}</div></section>`;
}
function journalSummaryMarkup(){const s=journalData().summary;return metric('Recorded days',fmt(s.entry_count),s.entry_count===1?'day':'days')+metric('Avg calories',fmt(s.average_calories),'kcal')+balanceMetric('Period balance',s.total_deficit,dayCount(s.deficit_days));}
function journalListMarkup(){
  const {source,end,count,pages}=journalDays();journalPage=Math.max(0,Math.min(journalPage,pages-1));
  const rows=new Map(source.entries.map(row=>[row.date,row]));
  let html='<div class="journal-columns journal-labels"><span>Date</span><span>Weight</span><span>Calories</span><span>Balance</span><span>Status</span><span></span></div>';
  for(let index=journalPage*JOURNAL_PAGE_SIZE;index<Math.min(count,(journalPage+1)*JOURNAL_PAGE_SIZE);index++){
    const day=shiftDate(end,-index),row=rows.get(day),balance=row?.deficit;
    html+=`<button class="journal-row journal-columns ${day===state.today&&!archiveView?'is-today':''}" data-day-cell="${day}" data-action="open-day" data-date="${day}" aria-label="Open ${day}"><span class="journal-date">${dateText(day,{day:'numeric',month:'short',year:'numeric'})}</span><span class="${row?.weight==null?'empty-value':''}">${fmt(row?.weight,1)}${row?.weight!=null?'<small>kg</small>':''}</span><span class="${row?.calories==null?'empty-value':isManualCalories(row)?'manual-value':''}" ${isManualCalories(row)?'title="Manual calories"':''}>${fmt(row?.calories)}${row?.calories!=null?'<small>kcal</small>':''}</span><span class="${balance==null?'empty-value':balance>=0?'green':'rose'}">${balance==null?'No data':`${fmt(Math.abs(balance))}<small>${balance>0?'deficit':balance<0?'surplus':'balanced'}</small>`}</span><span>${dayStatus(row,day)}</span>${icon('chevron')}</button>`;
  }return html;
}
function journalFooterMarkup(){const {source,end,count,pages}=journalDays();return `<span>${dateText(source.journal_start)} – ${dateText(end,{day:'numeric',month:'short',year:'numeric'})}${archiveView?' · Read-only archive':''}</span><div class="journal-pagination"><span>${journalPage*JOURNAL_PAGE_SIZE+1}–${Math.min(count,(journalPage+1)*JOURNAL_PAGE_SIZE)} of ${dayCount(count)}</span><button class="icon-button" data-action="journal-page" data-delta="-1" aria-label="Newer days" ${journalPage===0?'disabled':''}>${icon('back')}</button><button class="icon-button" data-action="journal-page" data-delta="1" aria-label="Older days" ${journalPage>=pages-1?'disabled':''}>${icon('chevron')}</button></div>`;}
async function selectArchive(value){const request=++archiveLoadSequence;try{await flushAll();const next=value==='current'?null:await api(`/api/archives/${value}`);if(request!==archiveLoadSequence)return;archiveView=next;journalPage=0;if(page==='history')renderHistory();}catch(error){toast(error.message);if(page==='history')renderHistory();}}

function renderInsights(){
  content.innerHTML=header('Insights')+`<section class="page-body insights-body" data-layout="page-body"><section class="metrics" id="insight-metrics">${summaryMarkup(true)}</section><section class="insight-context" id="goal-context">${goalContextMarkup()}</section><section class="insight-context" id="weekly-context">${weeklyContextMarkup()}</section><section class="chart-section compact-chart" data-layout="chart"><div class="section-head"><div class="chart-tabs" role="tablist" aria-label="Chart"><button role="tab" aria-selected="${insightKind==='weight'}" data-action="insight-kind" data-kind="weight" class="${insightKind==='weight'?'active':''}">Weight</button><button role="tab" aria-selected="${insightKind==='calories'}" data-action="insight-kind" data-kind="calories" class="${insightKind==='calories'?'active':''}">Calories</button></div>${ranges()}</div><div id="insight-plot" class="chart-wrap">${chartMarkup(insightKind,true)}</div><div class="chart-legend" id="insight-legend">${insightLegendMarkup()}</div></section></section>`;
}
function renderSettings(){
  const s=state.settings,opts={kind:'settings'};
  const fields=field('Name','name',s.name,{...opts,type:'text',placeholder:''})+field('Age','age',s.age,{...opts,unit:'years',min:18,max:120})+field('Height','height',s.height,{...opts,unit:'cm',min:50,max:250})+field('Sex · BMR formula','sex',s.sex,{...opts,options:[['','Select'],['male','Male'],['female','Female']]})+field('Goal weight','goal_weight',s.goal_weight,{...opts,unit:'kg',min:20,max:500})+field('Default training intensity','training_met',s.training_met,{...opts,unit:'MET',min:1,max:25,placeholder:'2.25',help:'Standard MET intensity. The default 2.25 is a light-intensity assumption; choose the intensity for your activity.'});
  content.innerHTML=header('Settings')+`<section class="page-body settings-body" data-layout="page-body"><section class="settings-profile"><div class="section-head"><h2>Profile</h2></div><form class="settings-form" autocomplete="off"><div class="field-grid">${fields}</div></form><div class="panel-footer"><button class="button subtle" data-action="formulas">${icon('info')}Formulas</button></div></section><section class="settings-data"><div class="section-head"><h2>Data</h2></div><div class="data-actions"><button class="button subtle" data-action="export" data-format="json">${icon('download')}Export all data</button><button class="button subtle" data-action="export" data-format="csv">${icon('download')}Export CSV</button><button class="button subtle danger" data-action="clear-history">${icon('trash')}Clear history</button></div></section></section>`;
}
function render(){
  document.querySelectorAll('nav a').forEach(a=>{a.classList.toggle('active',a.dataset.page===page);if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  ({overview:renderOverview,history:renderHistory,insights:renderInsights,settings:renderSettings}[page]||renderOverview)();
  document.title=`${{overview:'Overview',history:'Daily journal',insights:'Insights',settings:'Settings'}[page]} · Lean Plan`;
  status();
}
function refreshPanels(){
  if(!state)return;
  const replace=(id,html)=>{const el=document.getElementById(id);if(el)el.innerHTML=html;};
  replace('overview-readouts',summaryMarkup());replace('insight-metrics',summaryMarkup(true));replace('weight-plot',chartMarkup('weight',true));replace('insight-plot',chartMarkup(insightKind,true));replace('insight-legend',insightLegendMarkup());replace('goal-context',goalContextMarkup());replace('weekly-context',weeklyContextMarkup());replace('nutrition-tef',nutritionTefMarkup());replace('training-energy',derivedMarkup('Training energy',state.today_stats.training_kcal));
  if(page==='history'){replace('journal-summary',journalSummaryMarkup());replace('journal-table',journalListMarkup());replace('journal-footer',journalFooterMarkup());const archiveButton=document.querySelector('[data-action=archive-period]');if(archiveButton)archiveButton.disabled=!!archiveView||!state.entries.some(r=>r.date<state.today&&r.has_data);}
  syncWeightEditor();
  syncCalorieEditors();
  document.querySelectorAll('[data-nutrition]').forEach(el=>el.innerHTML=nutritionMarkup(el.dataset.nutrition));
  if(modalKind==='day')refreshDayDetail();
}
function openModal(html,kind){
  previousFocus=document.activeElement;modalKind=kind;modalRoot.innerHTML=`<div class="modal-backdrop"><section class="modal ${kind==='onboarding'?'onboarding':kind==='day'?'day-dialog':kind==='formulas'?'formula-dialog':kind==='archive'?'archive-dialog':'confirm-dialog'}" role="dialog" aria-modal="true" aria-labelledby="modal-title">${html}</section></div>`;
  setTimeout(()=>{if(!modalRoot.contains(document.activeElement))modalRoot.querySelector('button:not(:disabled),input,select')?.focus();},20);
}
function closeModal(){modalRoot.innerHTML='';modalKind='';modalDate=null;modalArchive=null;previousFocus?.focus();flushAll().catch(()=>{});}
function modalHead(title){return `<div class="modal-head"><h2 id="modal-title">${title}</h2><button class="icon-button" data-action="close" aria-label="Close">${icon('close')}</button></div>`;}
function dayModal(day,tab='measurements'){
  if(day>state.today)return;
  modalArchive=page==='history'?archiveView:null;modalDate=day;dayTab=tab;
  const row=dayData().entries.find(entry=>entry.date===day),opts={kind:'entry',day};
  openModal(`${modalHead(dateText(day,{day:'numeric',month:'long',year:'numeric'}))}<div class="day-meta" id="day-status">${dayStatus(row,day)}</div><div class="day-tabs" role="tablist" aria-label="Day details">${[['measurements','Measurements'],['activity','Activity']].map(([key,label])=>`<button role="tab" aria-selected="${tab===key}" data-action="day-tab" data-tab="${key}" class="${tab===key?'active':''}">${label}</button>`).join('')}</div><div class="day-pane" data-day-pane="measurements" ${tab==='measurements'?'':'hidden'}>${dayMeasurementsMarkup(day)}<div class="day-calculations" id="day-calculations"></div></div><div class="day-pane" data-day-pane="activity" ${tab==='activity'?'':'hidden'}><form class="field-grid" autocomplete="off">${field('Training time','training_minutes',row?.training_minutes,{...opts,unit:'min',min:0,max:1440,id:'day-training'})}<div id="day-training-energy"></div>${field('Steps','steps',row?.steps,{...opts,min:0,max:200000,id:'day-steps',help:'Step count is a separate log. Walking energy supplies the active kcal.'})}${field('Walking energy','steps_kcal',row?.steps_kcal,{...opts,unit:'kcal',min:0,max:20000,id:'day-walking',help:'Active walking kcal only, excluding resting energy and separately logged training.'})}</form></div><div class="modal-footer"><button class="button subtle danger" data-action="delete" data-date="${day}" ${row?'':'disabled'}>${icon('trash')}Delete day</button></div>`,'day');
  document.querySelector('#day-calculations').innerHTML=`<div class="day-calorie derived-field"><span>Calories</span>${calorieEditorMarkup(day,'day')}</div><div id="day-derived-calculations"></div>`;
  if(modalArchive){modalRoot.querySelectorAll('[data-kind]').forEach(input=>input.disabled=true);modalRoot.querySelector('.modal-footer').innerHTML='<span class="archive-readonly">Read-only archive</span>';}
  refreshDayDetail();
}
function refreshDayDetail(){
  const source=dayData(),row=source.entries.find(entry=>entry.date===modalDate),prior=[...source.entries].reverse().find(entry=>entry.date<modalDate&&entry.weight!=null)||source.baseline;
  const computed=row||calculate({date:modalDate},source.settings,prior?.weight??null,prior?.date??null);
  document.querySelector('#day-status').innerHTML=row?.has_data&&!row.entered_late&&modalDate!==state.today?'<span class="recorded-label">Recorded</span>':dayStatus(row,modalDate);
  document.querySelector('#day-derived-calculations').innerHTML=derivedMarkup('TEF',computed.tef,1)+derivedMarkup('BMR',computed.bmr)+derivedMarkup(computed.deficit==null?'Balance':computed.deficit>=0?'Deficit':'Surplus',computed.deficit==null?null:Math.abs(computed.deficit),0,computed.deficit==null?'':computed.deficit>=0?'green':'rose');
  syncCalorieEditors();
  const deleteButton=document.querySelector('[data-action=delete]');if(deleteButton)deleteButton.disabled=!row;
  const training=document.querySelector('#day-training-energy');if(training)training.innerHTML=derivedMarkup('Training energy',computed.training_kcal);
}
function deleteModal(day=null){
  const title=day?'Delete this day?':'Clear history?';
  openModal(`${modalHead(title)}<p class="confirm-copy">${day?dateText(day,{day:'numeric',month:'long',year:'numeric'}):'All current days and saved archives will be removed. Your profile stays.'}</p><div class="modal-footer"><button class="button subtle" data-action="close">Cancel</button><button class="button danger-fill" data-action="confirm-delete" ${day?`data-date="${day}"`:''}>${icon('trash')}${day?'Delete day':'Clear history'}</button></div><p class="error-message" role="alert"></p>`,'delete');
}
async function confirmDelete(button){
  button.disabled=true;
  try{await flushAll();base=await api(button.dataset.date?'/api/delete':'/api/history/clear',button.dataset.date?{date:button.dataset.date}:{confirmation:'CLEAR'});baseVersion++;archiveLoadSequence++;archiveView=null;journalPage=0;rebuild();closeModal();render();}catch(error){modalRoot.querySelector('.error-message').textContent=error.message;button.disabled=false;}
}
async function archiveModal(){
  try{await flushAll();const completed=state.entries.filter(r=>r.date<state.today&&r.has_data);if(!completed.length){toast('There are no completed days to archive yet.');return;}
    openModal(`${modalHead('Archive current period?')}<p class="confirm-copy">${dateText(state.journal_start)} – ${dateText(shiftDate(state.today,-1),{day:'numeric',month:'short',year:'numeric'})} · ${completed.length} recorded ${completed.length===1?'day':'days'}</p>${field('Period name','period_name',`Period ${(state.archives?.length||0)+1}`,{type:'text',id:'archive-name',placeholder:'e.g. Cut · autumn'})}<p class="archive-explanation">Completed days stay in this archive. Today’s entries stay in the new period, with a fresh balance.</p><div class="modal-footer"><button class="button subtle" data-action="close">Cancel</button><button class="button primary" data-action="confirm-archive">${icon('archive')}Archive & start new</button></div><p class="error-message" role="alert"></p>`,'archive');
  }catch(error){toast(error.message);}
}
async function confirmArchive(button){button.disabled=true;try{await flushAll();base=await api('/api/period/archive',{name:document.querySelector('#archive-name').value});baseVersion++;archiveLoadSequence++;archiveView=null;journalPage=0;rebuild();closeModal();render();toast('Period archived. Current balance starts from today.');}catch(error){modalRoot.querySelector('.error-message').textContent=error.message;button.disabled=false;}}
function wizard(){
  const s=state.settings,opts={kind:'settings'};
  const body=wizardStep===0?`<div class="field-grid">${field('Name','name',s.name,{...opts,type:'text',placeholder:''})}${field('Age','age',s.age,{...opts,unit:'years',min:18,max:120})}${field('Height','height',s.height,{...opts,unit:'cm',min:50,max:250})}${field('Sex · BMR formula','sex',s.sex,{...opts,options:[['','Select'],['male','Male'],['female','Female']]})}</div>`:`<div class="field-grid">${field('Today’s weight','weight',state.entries.find(row=>row.date===state.today)?.weight,{kind:'entry',day:state.today,unit:'kg',min:20,max:500,id:'setup-weight'})}${field('Goal weight · optional','goal_weight',s.goal_weight,{...opts,unit:'kg',min:20,max:500})}</div>`;
  openModal(`<div class="wizard-brand"><img src="/icon.svg" alt="" width="34" height="34"><span>lean<span>plan</span></span></div><div class="wizard-progress"><i class="active"></i><i class="${wizardStep===1?'active':''}"></i></div><div class="wizard-heading"><h2 id="modal-title">${wizardStep===0?'Your profile':'Starting point'}</h2><small>${wizardStep+1} / 2</small></div><form class="wizard-form">${body}<div class="wizard-actions"><button type="button" class="button text-button" data-action="setup-done">Skip for now</button><div>${wizardStep?'<button type="button" class="button subtle" data-action="setup-back">Back</button>':''}<button type="button" data-action="${wizardStep===0?'setup-next':'setup-done'}" class="button primary">${wizardStep===0?'Continue':'Done'}${icon('arrow')}</button></div></div></form>`,'onboarding');
}
function finishSetup(){stage('settings',null,'onboarding_done',true);closeModal();render();}
function navigate(next){if(!['overview','history','insights','settings'].includes(next))next='overview';if(next===page)return;page=next;history.replaceState(null,'',`#${page}`);render();flushAll().catch(()=>{});}
async function download(format){
  try{await flushAll();const suffix=format==='csv'&&page==='history'&&archiveView?`?archive=${archiveView.id}`:'',response=await fetch(`/api/export/${format}${suffix}`);if(!response.ok)throw new Error('Export failed.');const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`leanplan-${suffix?'archive-'+archiveView.id:state.today}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(error){toast(error.message);}
}
function inputChanged(input){
  if(!input.matches('[data-kind]'))return;
  if(input.id==='latest-weight-input')syncWeightEmptyLabel(input);
  if(input.name==='calorie_override')syncCaloriePresentation(input);
  if(input.type==='number'&&(!input.validity.valid||input.validity.badInput)){input.setAttribute('aria-invalid','true');return;}
  input.removeAttribute('aria-invalid');
  const value=input.type==='number'?(input.value===''?null:Number(input.value)):input.name==='sex'&&input.value===''?null:input.value;
  stage(input.dataset.kind,input.dataset.date||state.today,input.name,value);
}
document.addEventListener('input',event=>inputChanged(event.target));
document.addEventListener('change',event=>{
  const input=event.target;
  if(input.id==='journal-period'){selectArchive(input.value);return;}
  if(input.tagName==='SELECT')inputChanged(input);
  if(input.matches('[data-kind]'))flushAll().catch(()=>{});
});
document.addEventListener('focusout',event=>{if(event.target.matches('[data-kind]'))flushAll().catch(()=>{});});
document.addEventListener('submit',event=>{event.preventDefault();if(event.target.matches('.wizard-form')){if(wizardStep===0){wizardStep=1;wizard();}else finishSetup();}else flushAll().catch(()=>{});});
document.addEventListener('click',async event=>{
  const nav=event.target.closest('[data-page]');if(nav){event.preventDefault();navigate(nav.dataset.page);return;}
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const action=button.dataset.action;
  if(action==='range'){chartRange=Number(button.dataset.days);document.querySelectorAll('[data-action=range]').forEach(el=>{el.classList.toggle('active',Number(el.dataset.days)===chartRange);el.setAttribute('aria-pressed',String(Number(el.dataset.days)===chartRange));});refreshPanels();}
  else if(action==='open-day')dayModal(button.dataset.date);
  else if(action==='open-activity')dayModal(state.today,'activity');
  else if(action==='day-tab')selectDayTab(button.dataset.tab);
  else if(action==='insight-kind'){insightKind=button.dataset.kind;document.querySelectorAll('[data-action=insight-kind]').forEach(el=>{el.classList.toggle('active',el.dataset.kind===insightKind);el.setAttribute('aria-selected',String(el.dataset.kind===insightKind));});refreshPanels();}
  else if(action==='formulas')formulasModal();
  else if(action==='close')closeModal();
  else if(action==='delete')deleteModal(button.dataset.date);
  else if(action==='clear-history')deleteModal();
  else if(action==='confirm-delete')await confirmDelete(button);
  else if(action==='archive-period')await archiveModal();
  else if(action==='confirm-archive')await confirmArchive(button);
  else if(action==='export')download(button.dataset.format);
  else if(action==='setup-done')finishSetup();
  else if(action==='setup-next'){wizardStep=1;wizard();}
  else if(action==='setup-back'){wizardStep=0;wizard();}
  else if(action==='journal-page'){journalPage+=Number(button.dataset.delta);renderHistory();}
});
document.addEventListener('keydown',event=>{
  if(!modalKind)return;
  if(event.key==='Escape'&&modalKind!=='onboarding'){closeModal();return;}
  if(event.key==='Tab'){const focusable=[...modalRoot.querySelectorAll('button:not(:disabled),input,select,textarea,summary')].filter(el=>el.getClientRects().length),first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
});
function showTooltip(target,x,y){const row=state.entries.find(entry=>entry.date===target.dataset.chartDate);if(!row)return;const manual=target.dataset.chartKind==='calories'&&isManualCalories(row),frame=document.querySelector('#app-frame').getBoundingClientRect();x=(x-frame.left)/window.leanplanScale;y=(y-frame.top)/window.leanplanScale;const el=document.querySelector('#chart-tooltip');el.innerHTML=`<strong>${dateText(row.date)}</strong><span class="${manual?'manual-value':''}">${target.dataset.chartKind==='weight'?`${fmt(row.weight,1)} kg · mean ${fmt(row.weight_average,2)}`:`${fmt(row.calories)} kcal${manual?' · Manual':''}`}</span>${row.entered_late?'<small>Late entry</small>':''}`;el.style.display='block';el.style.left=`${Math.min(x+12,1200-210)}px`;el.style.top=`${Math.max(8,y-80)}px`;}
document.addEventListener('pointerover',event=>{const hit=event.target.closest('[data-chart-date]');if(hit)showTooltip(hit,event.clientX,event.clientY);});
document.addEventListener('pointerout',event=>{if(event.target.closest('[data-chart-date]'))document.querySelector('#chart-tooltip').style.display='none';});
document.addEventListener('focusin',event=>{const hit=event.target.closest('[data-chart-date]');if(hit){const rect=hit.getBoundingClientRect();showTooltip(hit,rect.x,rect.y);}else document.querySelector('#chart-tooltip').style.display='none';});
window.addEventListener('beforeunload',event=>{if(window.leanplanPending){flushAll().catch(()=>{});event.preventDefault();event.returnValue='';}});
async function refreshDay(){
  if(!base)return;
  try{await flushAll();const version=baseVersion;const next=await api('/api/state');if(version!==baseVersion)return;const changed=next.today!==base.today;base=next;baseVersion++;rebuild();if(archiveView&&!state.archives.some(a=>a.id===archiveView.id))archiveView=null;if(changed){if(modalKind==='day')closeModal();journalPage=0;render();}else refreshPanels();}catch{}
}
window.refreshDay=refreshDay;
window.addEventListener('focus',refreshDay);
setInterval(refreshDay,30000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')flushAll().catch(()=>{});else refreshDay();});
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)||'overview'));

function derivedMarkup(label,value,digits=0,tone=''){return `<div class="derived-field ${value==null?'is-empty':''}"><span>${label}</span><strong class="${tone}">${fmt(value,digits)}${value!=null?'<small>kcal</small>':''}</strong></div>`;}
function overviewEditorMarkup(){
  const day=state.today,row=state.entries.find(entry=>entry.date===day)||{},opts={kind:'entry',day};
  return `<div class="nutrition-content"><div class="nutrition-totals" id="nutrition-totals">${nutritionTotalsMarkup()}</div><form class="macro-editor" autocomplete="off">${[['Protein','protein',1000],['Carbs','carbs',2000],['Fat','fat',1000]].map(([label,key,max])=>field(label,key,row[key],{...opts,unit:'g',min:0,max,id:`today-${key}`})).join('')}</form></div>`;
}
function nutritionTotalsMarkup(){return calorieEditorMarkup(state.today,'today')+`<div id="nutrition-tef">${nutritionTefMarkup()}</div>`;}
function nutritionTefMarkup(){const t=state.today_stats;return `<div class="tef-total"><span>TEF</span><strong class="${t.tef==null?'empty-value':''}">${fmt(t.tef,1)}${t.tef!=null?'<small>kcal</small>':''}</strong></div>`;}
function calorieEditorRow(day,context){const source=context==='day'?dayData():state;return source.entries.find(row=>row.date===day)||{};}
function automaticCalories(row){return Object.hasOwn(row,'calculated_calories')?row.calculated_calories:row.calories??null;}
function calorieEditorMarkup(day,context){
  const row=calorieEditorRow(day,context),auto=automaticCalories(row),manual=isManualCalories(row),empty=row.calorie_override==null&&auto==null;
  return `<div class="calorie-editor ${empty?'is-empty':''}" data-calorie-context="${context}"><input id="${context}-calories" aria-label="Calories" name="calorie_override" type="number" min="0" max="50000" step="any" inputmode="decimal" data-kind="entry" data-date="${day}" value="${esc(row.calorie_override??'')}" placeholder="${auto!=null?fmt(auto):''}" class="${manual?'manual-value':''}" title="${manual?'Manual calories. Clear to calculate from macros.':'Calculated from macros. Enter your own calories to override.'}"><small>kcal</small><span class="calorie-empty">No data</span></div>`;
}
function syncCaloriePresentation(input){
  input.parentElement.classList.toggle('is-empty',input.value===''&&input.placeholder===''&&!input.validity.badInput);
  input.classList.toggle('manual-value',input.value!=='');
  const description=input.value!==''?'Manual calories. Clear to calculate from macros.':'Calculated from macros. Enter your own calories to override.';
  input.title=description;input.setAttribute('aria-description',description);
}
function syncCalorieEditors(){
  document.querySelectorAll('[data-calorie-context] input').forEach(input=>{
    const row=calorieEditorRow(input.dataset.date,input.parentElement.dataset.calorieContext),auto=automaticCalories(row);
    if(document.activeElement!==input&&!input.hasAttribute('aria-invalid'))input.value=row.calorie_override??'';
    input.placeholder=auto!=null?fmt(auto):'';
    syncCaloriePresentation(input);
  });
}
function overviewActivityMarkup(){
  const day=state.today,row=state.entries.find(entry=>entry.date===day)||{},opts={kind:'entry',day};
  return `<form class="activity-editor" autocomplete="off"><div class="activity-inputs">${field('Training time','training_minutes',row.training_minutes,{...opts,unit:'min',min:0,max:1440,id:'today-training'})}<div id="training-energy">${derivedMarkup('Training energy',state.today_stats.training_kcal)}</div>${field('Steps','steps',row.steps,{...opts,min:0,max:200000,id:'today-steps',help:'Step count is a separate log. Active walking kcal are entered in Walking energy and counted once.'})}${field('Walking energy','steps_kcal',row.steps_kcal,{...opts,unit:'kcal',min:0,max:20000,id:'today-walking',help:'Active walking kcal only, excluding resting energy and any training logged separately.'})}</div></form>`;
}
function weightMetricMarkup(){
  const row=state.entries.find(entry=>entry.date===state.today)||{},s=state.summary;
  return `<article class="metric weight-metric"><label for="latest-weight-input">Latest weight ${icon('edit')}</label><div class="metric-input ${s.latest_weight==null?'is-empty':''}"><input id="latest-weight-input" aria-label="Latest weight" name="weight" type="number" min="20" max="500" step="any" inputmode="decimal" data-kind="entry" data-date="${state.today}" value="${esc(row.weight??'')}" placeholder="${s.latest_weight!=null?fmt(s.latest_weight,1):''}"><small>kg</small><span class="weight-empty">No data</span></div><small id="weight-measured-on">${s.latest_weight_date?dateText(s.latest_weight_date):''}</small></article>`;
}
function syncWeightEmptyLabel(input){
  input.parentElement.classList.toggle('is-empty',input.value===''&&input.placeholder===''&&!input.validity.badInput);
}
function syncWeightEditor(){
  const input=document.querySelector('#latest-weight-input');if(!input)return;
  const row=state.entries.find(entry=>entry.date===state.today)||{};
  if(document.activeElement!==input&&!input.hasAttribute('aria-invalid'))input.value=row.weight??'';
  input.placeholder=state.summary.latest_weight!=null?fmt(state.summary.latest_weight,1):'';
  syncWeightEmptyLabel(input);
  document.querySelector('#weight-measured-on').textContent=state.summary.latest_weight_date?dateText(state.summary.latest_weight_date):'';
}
function dayMeasurementsMarkup(day){
  const source=dayData(),row=source.entries.find(entry=>entry.date===day)||{},prior=[...source.entries].reverse().find(entry=>entry.date<day&&entry.weight!=null)||source.baseline,opts={kind:'entry',day};
  return `<form class="day-measurements" autocomplete="off">${field('Weight','weight',row.weight,{...opts,unit:'kg',min:20,max:500,id:'day-weight',placeholder:prior?fmt(prior.weight,1):''})}${[['Protein','protein',1000],['Fat','fat',1000],['Carbs','carbs',2000]].map(([label,key,max])=>field(label,key,row[key],{...opts,unit:'g',min:0,max,id:`day-${key}`})).join('')}</form>${row.weight==null&&prior?`<div class="carried-weight">Weight from ${dateText(prior.date)}</div>`:'<div class="carried-weight"></div>'}`;
}
function selectDayTab(tab){dayTab=tab;document.querySelectorAll('[data-day-pane]').forEach(el=>el.hidden=el.dataset.dayPane!==tab);document.querySelectorAll('[data-action=day-tab]').forEach(el=>{el.classList.toggle('active',el.dataset.tab===tab);el.setAttribute('aria-selected',String(el.dataset.tab===tab));});}


function goalContextMarkup(){
  const s=state.summary,g=state.settings.goal_weight;
  return `<div class="context-title"><h2>Weight goal</h2><strong class="${g==null?'empty-value':''}">${fmt(g,1)}${g!=null?'<small>kg</small>':''}</strong></div><div class="context-progress ${s.goal_progress==null?'no-progress':''}"><div class="goal-track" role="progressbar" aria-label="Weight goal progress" ${s.goal_progress!=null?`aria-valuenow="${s.goal_progress}"`:''} aria-valuemin="0" aria-valuemax="100"><i style="width:${s.goal_progress??0}%"></i></div><span>${s.goal_progress==null?'No data':`${fmt(s.goal_progress)}%`}</span></div>`;
}
function weeklyContextMarkup(){
  const s=state.summary;
  return `<div class="context-title"><h2>7-day averages</h2></div><div class="weekly-values">${[['This week',s.recent_average],['Previous week',s.previous_average]].map(([label,value])=>`<div><span>${label}</span><strong class="${value==null?'empty-value':''}">${fmt(value,2)}${value!=null?'<small>kg</small>':''}</strong></div>`).join('')}</div>`;
}

function insightLegendMarkup(){return insightKind==='weight'?'<span><i></i>Weight</span><span><i class="mean"></i>7-day mean</span>':'<span><i></i>Calculated</span><span><i class="manual"></i>Manual</span><span><i class="late"></i>Late entry</span>';}
function formulasModal(){openModal(`${modalHead('Formulas')}<dl class="formulas"><dt>Calories</dt><dd>Protein × 4 + fat × 9 + carbs × 4<small>A manual calorie value takes priority; clear it to use macros.</small></dd><dt>TEF estimate</dt><dd>Protein × 1 + carbs × 0.3 + fat × 0.18<small>25% of protein, 7.5% of carb and 2% of fat energy.</small></dd><dt>BMR</dt><dd>10 × kg + 6.25 × cm − 5 × age + sex constant<small>Mifflin–St Jeor, adults. Male +5; female −161.</small></dd><dt>Net training</dt><dd>Minutes × (MET − 1) × 3.5 × kg ÷ 200<small>Activity above the standard 1-MET resting level.</small></dd><dt>Walking</dt><dd>Entered active walking kcal only.<small>Steps are logged separately and do not add more kcal.</small></dd><dt>Balance</dt><dd>BMR + net training + walking + TEF − calories</dd></dl><p class="formula-note">Energy values are estimates. Unlogged activity is not included.</p>`,'formulas');}
function fitCanvas(){
  const width=1200,height=780,scale=Math.min(innerWidth/width,innerHeight/height),frame=document.querySelector('#app-frame');
  frame.style.transform=`scale(${scale})`;frame.style.left=`${(innerWidth-width*scale)/2}px`;frame.style.top=`${(innerHeight-height*scale)/2}px`;window.leanplanScale=scale;
}
window.addEventListener('resize',fitCanvas);
document.addEventListener('keydown',event=>{if(event.key==='F11'||((event.ctrlKey||event.metaKey)&&['+','-','=','0'].includes(event.key)))event.preventDefault();});
document.addEventListener('wheel',event=>{if(event.ctrlKey)event.preventDefault();},{passive:false});
fitCanvas();

async function init(){
  document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
  try{base=await api('/api/state');if(!base.journal_start)throw new Error('Reopen Lean Plan.');rebuild();page=['overview','history','insights','settings'].includes(location.hash.slice(1))?location.hash.slice(1):'overview';render();if(!state.settings.onboarding_done)wizard();}catch{content.innerHTML='<div class="load-error">Reopen Lean Plan to load the updated journal.</div>';}
}
init();
