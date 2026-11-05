"use strict";
(()=>{
 const toggle=$('navigation-toggle'),sidebar=$('main-navigation');let timer=null,inflight=false,again=false;
 const fresh=new Set(['appendices-button','image-activation-button','content-flags-button','agents-button','design-button']);
 function setOpen(open){sidebar.hidden=!open;document.body.classList.toggle('navigation-collapsed',!open);toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'Navigation einklappen':'Navigation ausklappen');try{localStorage.setItem('onescm-navigation-open',String(open));}catch{}}
 let open=window.innerWidth>800;try{const value=localStorage.getItem('onescm-navigation-open');if(value!==null)open=value==='true';}catch{}setOpen(open);
 toggle.onclick=()=>{setOpen(sidebar.hidden);if(!sidebar.hidden)schedule();};
 sidebar.addEventListener('keydown',e=>{if(e.key==='Escape'){setOpen(false);toggle.focus();}});
 sidebar.querySelectorAll('button[id]').forEach(button=>{button.dataset.navLabel=button.textContent;});
 async function refresh(){if(!meta?.token)return;if(inflight){again=true;return;}inflight=true;try{const data=await api('/api/navigation/counts',{});for(const [id,value] of Object.entries(data)){const button=$(id);if(!button)continue;button.replaceChildren(document.createTextNode((button.dataset.navLabel||button.textContent)+' ('+(value.count===null?'—':value.count.toLocaleString('de-DE'))+')'));button.title=value.description;if(fresh.has(id)){const badge=document.createElement('span');badge.className='navigation-new';badge.textContent='Neu';button.append(' ',badge);}}}catch{sidebar.querySelectorAll('button[title]').forEach(b=>b.title+=' · Zähler möglicherweise veraltet');}finally{inflight=false;if(again){again=false;schedule();}}}
 function schedule(){clearTimeout(timer);timer=setTimeout(refresh,250);}
 window.addEventListener('onescm-data-change',schedule);window.addEventListener('focus',schedule);document.addEventListener('visibilitychange',()=>{if(!document.hidden)schedule();});
})();
