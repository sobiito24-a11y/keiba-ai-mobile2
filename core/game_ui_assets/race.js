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
document.addEventListener('toggle',resize,true);
let initial=0;try{initial=Number(sessionStorage.getItem('keiba-ui:'+data.race_key)||0);}catch(e){}
select(Number.isInteger(initial)&&initial>=0&&initial<data.cards.length?initial:0);
window.gameResizeObserver=new ResizeObserver(resize);window.gameResizeObserver.observe(document.body);
window.addEventListener('load',resize);
})();
