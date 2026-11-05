"use strict";
(()=>{
 const toggle=$('navigation-toggle'),sidebar=$('main-navigation');let timer=null,inflight=false,again=false;
 const fresh=new Set(['storage-button','appendices-button','image-activation-button','content-flags-button','agents-button','design-button']);
 function setOpen(open){sidebar.hidden=!open;document.body.classList.toggle('navigation-collapsed',!open);toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'Navigation einklappen':'Navigation ausklappen');try{localStorage.setItem('onescm-navigation-open',String(open));}catch{}}
 let open=window.innerWidth>800;try{const value=localStorage.getItem('onescm-navigation-open');if(value!==null)open=value==='true';}catch{}setOpen(open);
 toggle.onclick=()=>{setOpen(sidebar.hidden);if(!sidebar.hidden)schedule();};
 sidebar.addEventListener('keydown',e=>{if(e.key==='Escape'){setOpen(false);toggle.focus();}});
 const process=document.createElement('div');process.id='process-navigation';
 const groups=[['1 · Überblick',['dashboard-button','storage-button']],['2 · Quellen & Prüfung',['sources-button','content-flags-button','agents-button','jobs-button','conflicts-button']],['3 · Wissen & Anhänge',['rag-button','internal-button','chat-button','appendices-button','ai-exchange-button']],['4 · Struktur & Bilder',['overview-button','new-outline','import-outline','compare-button','image-activation-button']],['5 · Design & Ausgabe',['design-button','variants-button','markdown-tool','releases-button']],['6 · Sichern & Abschluss',['backup-button','project-status-button']]];
 for(const [index,[title,ids]] of groups.entries()){const group=document.createElement('details');group.className='process-group';group.open=true;const summary=document.createElement('summary');summary.textContent=title;group.append(summary);for(const id of ids){const button=$(id);if(button)group.append(button);}try{const saved=localStorage.getItem('onescm-process-'+index);if(saved!==null)group.open=saved==='true';}catch{}group.addEventListener('toggle',()=>{try{localStorage.setItem('onescm-process-'+index,String(group.open));}catch{}});process.append(group);}
 sidebar.insertBefore(process,$('outline-list'));
 sidebar.querySelectorAll('button[id]').forEach(button=>{button.dataset.navLabel=button.textContent;});
 async function refresh(){if(!meta?.token)return;if(inflight){again=true;return;}inflight=true;try{const data=await api('/api/navigation/counts',{});for(const [id,value] of Object.entries(data)){const button=$(id);if(!button)continue;button.replaceChildren(document.createTextNode((button.dataset.navLabel||button.textContent)+' ('+(value.count===null?'—':value.count.toLocaleString('de-DE'))+')'));button.title=value.description;if(fresh.has(id)){const badge=document.createElement('span');badge.className='navigation-new';badge.textContent='Neu';button.append(' ',badge);}}}catch{sidebar.querySelectorAll('button[title]').forEach(b=>b.title+=' · Zähler möglicherweise veraltet');}finally{inflight=false;if(again){again=false;schedule();}}}
 function schedule(){clearTimeout(timer);timer=setTimeout(refresh,250);}
 window.addEventListener('onescm-data-change',schedule);window.addEventListener('focus',schedule);document.addEventListener('visibilitychange',()=>{if(!document.hidden)schedule();});
})();
