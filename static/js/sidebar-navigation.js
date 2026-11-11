(() => {
    'use strict';
    const region=document.querySelector('[data-sidebar-region]');
    if(!region)return;
    const scroller=region.querySelector('.sidebar-scroll');
    const up=region.querySelector('[data-sidebar-scroll=up]'),down=region.querySelector('[data-sidebar-scroll=down]');
    const active=scroller.querySelector('.sidebar-link[aria-current=page],.sidebar-link.active');
    const activeHref=active?.getAttribute('href')||location.pathname;
    const storageKey='cq.sidebar.position.'+region.dataset.scrollOwner;
    scroller.querySelectorAll('.sidebar-link').forEach(link=>{
        const label=link.querySelector('.nav-text')?.textContent.trim();
        if(label){if(!link.hasAttribute('aria-label'))link.setAttribute('aria-label',label);if(!link.title)link.title=label;}
    });
    let frame=0,saveTimer=0;
    const save=()=>{try{sessionStorage.setItem(storageKey,JSON.stringify({top:scroller.scrollTop,active:activeHref}));}catch{}};
    function update(){
        frame=0;
        const overflow=scroller.scrollHeight>region.clientHeight+2;
        up.hidden=down.hidden=!overflow;
        const limit=scroller.scrollHeight-scroller.clientHeight;
        up.disabled=scroller.scrollTop<=1;
        down.disabled=scroller.scrollTop>=limit-1;
    }
    const schedule=()=>{if(!frame)frame=requestAnimationFrame(update);};
    function revealActive(){
        if(!active)return;
        if(active===scroller.querySelector('.sidebar-link')){scroller.scrollTop=0;return;}
        const item=active.getBoundingClientRect(),box=scroller.getBoundingClientRect();
        if(item.top<box.top+8)scroller.scrollTop-=box.top+8-item.top;
        else if(item.bottom>box.bottom-8)scroller.scrollTop+=item.bottom-box.bottom+8;
    }
    function restore(){
        let previous=null;
        try{previous=JSON.parse(sessionStorage.getItem(storageKey));}catch{}
        update();
        if(previous&&Number.isFinite(previous.top))scroller.scrollTop=Math.max(0,previous.top);
        if(!previous||previous.active!==activeHref)revealActive();
        update();
        region.dataset.scrollReady='true';
    }
    [up,down].forEach(button=>button.addEventListener('click',()=>{
        scroller.scrollBy({top:(button===up?-1:1)*Math.max(120,scroller.clientHeight*.7),
            behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});
    }));
    scroller.addEventListener('scroll',()=>{schedule();clearTimeout(saveTimer);saveTimer=setTimeout(save,120);},{passive:true});
    scroller.addEventListener('keydown',event=>{
        if(event.target!==scroller)return;
        if(event.key==='Home'||event.key==='End'){
            event.preventDefault();scroller.scrollTo({top:event.key==='Home'?0:scroller.scrollHeight,behavior:'instant'});
        }
    });
    if(window.ResizeObserver){const observer=new ResizeObserver(schedule);observer.observe(scroller);observer.observe(scroller.querySelector('.sidebar-nav'));}
    window.addEventListener('resize',schedule,{passive:true});
    window.addEventListener('pagehide',save);
    window.addEventListener('pageshow',()=>requestAnimationFrame(restore));
    requestAnimationFrame(restore);
})();
