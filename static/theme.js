'use strict';
(() => {
 const apply=value=>document.documentElement.setAttribute('data-theme',value==='light'?'light':'dark');
 try{apply(localStorage.getItem('arena-theme'));}catch{apply('dark');}
 window.addEventListener('storage',event=>{if(event.key==='arena-theme')apply(event.newValue);});
})();
