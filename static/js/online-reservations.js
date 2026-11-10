(() => {
  const root=document.querySelector('[data-reservation-watch]');
  if(!root)return;
  let waiting=false;
  setInterval(async()=>{
    if(document.hidden||waiting)return;
    waiting=true;
    try{
      const response=await fetch(root.dataset.stateUrl,{credentials:'same-origin',headers:{'Accept':'application/json'}});
      if(!response.ok)return;
      const state=await response.json();
      const changed=String(state.revision)!==root.dataset.revision||state.status!==root.dataset.status||Number(state.received)!==Number(root.dataset.received)||Number(state.refunded)!==Number(root.dataset.refunded);
      if(changed){root.querySelector('[data-reservation-update]').hidden=false;}
    }catch{}finally{waiting=false;}
  },5000);
})();
