(()=>{
'use strict';
const data=JSON.parse(document.getElementById('race-data').textContent);
const host=document.getElementById('selected-card');
const buttons=[...document.querySelectorAll('[data-select]')];
let selected=-1;
function resize(){parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:Math.ceil(document.documentElement.getBoundingClientRect().height)},'*');}
function select(index,focusCard=false){
 if(index<0||index>=data.cards.length)return;
 selected=index;
 document.querySelectorAll('[data-row]').forEach((row,i)=>row.classList.toggle('selected',i===index));
 buttons.forEach((btn,i)=>btn.setAttribute('aria-pressed',String(i===index)));
 host.innerHTML=data.cards[index];
 document.getElementById('selection-status').textContent=data.names[index]+'を表示中';
 try{sessionStorage.setItem('keiba-ui:'+data.race_key,String(index));}catch(e){}
 if(focusCard){host.setAttribute('tabindex','-1');host.focus({preventScroll:true});}
 resize();
}
buttons.forEach((btn,i)=>{
 btn.addEventListener('click',()=>select(i));
 btn.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=Math.max(0,Math.min(buttons.length-1,i+(e.key==='ArrowDown'?1:-1)));buttons[n].focus();select(n);}});
});
document.querySelectorAll('[data-row]').forEach((row,i)=>row.addEventListener('click',e=>{if(!e.target.closest('button'))select(i);}));
function showMetric(key){
 const group=data.tabs.find(t=>t.key===key);if(!group)return;
 document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===key)));
 document.getElementById('metric-count').textContent=(key==='final'?'最終印候補 '+group.eligible:group.label+' · 該当'+group.eligible)+'頭／全'+group.total+'頭';
 document.getElementById('top-horses').classList.toggle('information',['information','candidates'].includes(group.kind));
 document.getElementById('top-horses').classList.toggle('candidate-layout',group.kind==='candidates');
 document.getElementById('top-horses').innerHTML=group.html;
 document.getElementById('metric-note').textContent=key==='final'?'＋／−は参考材料です。馬名または候補をタップすると、既存の詳細カードで根拠の全文を確認できます。':group.note;
 document.querySelectorAll('[data-top-select]').forEach(b=>b.addEventListener('click',()=>{select(Number(b.dataset.topSelect),true);host.scrollIntoView({block:'nearest',behavior:'smooth'});}));
 document.querySelectorAll('[data-candidate-select]').forEach(row=>row.addEventListener('click',e=>{if(!e.target.closest('button')){select(Number(row.dataset.candidateSelect),true);host.scrollIntoView({block:'nearest',behavior:'smooth'});}}));
 resize();
}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>showMetric(b.dataset.tab)));
showMetric('final');
document.addEventListener('toggle',resize,true);
let initial=0;try{initial=Number(sessionStorage.getItem('keiba-ui:'+data.race_key)||0);}catch(e){}
select(Number.isInteger(initial)&&initial>=0&&initial<data.cards.length?initial:0);
window.gameResizeObserver=new ResizeObserver(resize);window.gameResizeObserver.observe(document.body);
window.addEventListener('load',resize);
})();
