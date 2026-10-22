(()=>{
'use strict';
const data=JSON.parse(document.getElementById('race-data').textContent);
const host=document.getElementById('selected-card');
const buttons=[...document.querySelectorAll('[data-select]')];
let selected=-1;
function resize(){parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:Math.ceil(document.documentElement.getBoundingClientRect().height)},'*');}
const horseMap=new Map((data.horses||data.names.map((n,i)=>({no:n.split(' ')[0],sort:{}}))).map((h,i)=>[String(h.no),{...h,index:i}]));
let selectedHorse=null;
function selectHorse(no){
 no=String(no);const h=horseMap.get(no);if(!h)return;
 const old=document.querySelector('.lineup-detail');if(old)old.remove();
 document.querySelectorAll('[data-accordion]').forEach(b=>{b.setAttribute('aria-expanded','false');const p=document.getElementById(b.getAttribute('aria-controls'));p.hidden=true;p.innerHTML='';});
 document.getElementById('selected-section').hidden=true;
 document.querySelectorAll('[data-row]').forEach(r=>r.classList.toggle('selected',r.dataset.horse===no));
 if(selectedHorse===no){selectedHorse=null;resize();return;}
 selectedHorse=no;
 const row=document.querySelector('[data-horse="'+no+'"]');if(!row)return;
 const detail=document.createElement('tr');detail.className='lineup-detail';detail.dataset.detailHorse=no;
 const td=document.createElement('td');td.colSpan=row.children.length;td.innerHTML=data.cards[h.index];detail.appendChild(td);row.after(detail);
 document.getElementById('selection-status').textContent=data.names[h.index]+'を表示中';
 try{sessionStorage.setItem('keiba-ui:'+data.race_key,no);}catch(e){}
 resize();
}
function select(index){const h=data.horses[index];if(h)selectHorse(h.no);}
buttons.forEach(btn=>btn.addEventListener('click',()=>selectHorse(btn.dataset.select)));
document.querySelectorAll('[data-row]').forEach(row=>row.addEventListener('click',e=>{if(!e.target.closest('button'))selectHorse(row.dataset.horse);}));
function compareHorses(a,b,key,sign){
 const av=a.sort[key],bv=b.sort[key];
 const am=typeof av!=='number'||!Number.isFinite(av),bm=typeof bv!=='number'||!Number.isFinite(bv);
 if(am!==bm)return am?1:-1;
 if(!am&&av!==bv)return sign*(av-bv);
 if(am&&bm&&key==='score'){const ar=Number.isFinite(a.rank)?a.rank:Infinity,br=Number.isFinite(b.rank)?b.rank:Infinity;if(ar!==br)return ar-br;}
 return Number(a.no)-Number(b.no);
}
function sortCandidates(){
 const control=document.getElementById('candidate-sort');if(!control)return;
 const score=control.value==='score',key=score?'final_score':'no',sign=score?-1:1;
 const section=document.querySelector('.final-candidates');if(!section)return;
 section.dataset.order=control.value;
 section.querySelectorAll('.final-score').forEach(cell=>cell.hidden=!score);
 section.querySelector('.final-order-note').textContent=score?'選択中モデルの正式スコアが高い順。未取得は最後に表示します':'馬番順では最終評価スコアを表示しません';
 for(const container of section.querySelectorAll('.final-table tbody,.final-mobile')){
  const rows=[...container.children].filter(r=>r.hasAttribute('data-candidate-index'));
  rows.sort((a,b)=>compareHorses(data.horses[Number(a.dataset.candidateIndex)],data.horses[Number(b.dataset.candidateIndex)],key,sign));
  rows.forEach(row=>{
   container.appendChild(row);
   if(row.classList.contains('final-candidate-row')){
    const detail=container.querySelector('#final-desktop-detail-'+row.dataset.candidateIndex);if(detail)container.appendChild(detail);
   }
  });
 }
 resize();
}
function sortLineup(){
 const key=document.getElementById('lineup-sort').value;
 const sign=document.getElementById('lineup-direction').value==='asc'?1:-1;
 const body=document.querySelector('.table-scroll tbody');
 const rows=[...body.querySelectorAll('tr[data-horse]')];
 rows.sort((a,b)=>compareHorses(horseMap.get(a.dataset.horse),horseMap.get(b.dataset.horse),key,sign));
 rows.forEach(r=>{body.appendChild(r);const detail=body.querySelector('[data-detail-horse="'+r.dataset.horse+'"]');if(detail)body.appendChild(detail);});
 resize();
}
document.getElementById('lineup-sort').addEventListener('change',sortLineup);
document.getElementById('lineup-direction').addEventListener('change',sortLineup);
sortLineup();
function showMetric(key){
 const group=data.tabs.find(t=>t.key===key);if(!group)return;
 document.getElementById('selected-section').hidden=true;
 document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===key)));
 document.getElementById('metric-count').textContent=(key==='final'?'最終候補 '+group.eligible:group.label+' · 該当'+group.eligible)+'頭／全'+group.total+'頭';
 document.getElementById('top-horses').classList.toggle('information',['information','candidates'].includes(group.kind));
 document.getElementById('top-horses').classList.toggle('candidate-layout',group.kind==='candidates');
 document.getElementById('top-horses').innerHTML=group.html;
 document.getElementById('metric-note').textContent=key==='final'?'馬名を選ぶと詳細を開閉します。候補の選出・表示順で予想データは変わりません。':group.note;
 document.querySelectorAll('[data-top-select]').forEach(b=>b.addEventListener('click',()=>{select(Number(b.dataset.topSelect));}));
 document.querySelectorAll('[data-accordion]').forEach(btn=>btn.addEventListener('click',()=>accordion(Number(btn.dataset.accordion))));
 const candidateSort=document.getElementById('candidate-sort');if(candidateSort)candidateSort.addEventListener('change',sortCandidates);
 document.querySelectorAll('[data-final-toggle]').forEach(btn=>btn.addEventListener('click',()=>{
  const panel=document.getElementById(btn.getAttribute('aria-controls'));
  if(!panel)return;
  panel.hidden=!panel.hidden;btn.setAttribute('aria-expanded',String(!panel.hidden));resize();
 }));
 if(key==='final')sortCandidates();
 resize();
}
function accordion(index){
 const detail=document.querySelector('.lineup-detail');if(detail)detail.remove();selectedHorse=null;
 const btn=document.querySelector('[data-accordion="'+index+'"]');if(!btn)return;
 const opening=btn.getAttribute('aria-expanded')!=='true';
 document.querySelectorAll('[data-accordion]').forEach(b=>{
  b.setAttribute('aria-expanded','false');const panel=document.getElementById(b.getAttribute('aria-controls'));panel.hidden=true;panel.innerHTML='';
 });
 if(opening){btn.setAttribute('aria-expanded','true');const panel=document.getElementById(btn.getAttribute('aria-controls'));panel.innerHTML=data.cards[index];panel.hidden=false;}
 resize();
}
document.querySelectorAll('[data-conclusion]').forEach(b=>b.addEventListener('click',()=>{
 showMetric('final');const i=Number(b.dataset.conclusion);const target=document.querySelector('[data-accordion="'+i+'"]');
 if(target&&target.getAttribute('aria-expanded')!=='true')accordion(i);
}));
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>showMetric(b.dataset.tab)));
showMetric('final');
document.addEventListener('toggle',resize,true);
let initial=0;try{initial=Number(sessionStorage.getItem('keiba-ui:'+data.race_key)||0);}catch(e){}
// The final-candidate accordion owns initial selection; the all-runner panel opens on demand.
window.gameResizeObserver=new ResizeObserver(resize);window.gameResizeObserver.observe(document.body);
window.addEventListener('load',resize);
})();
