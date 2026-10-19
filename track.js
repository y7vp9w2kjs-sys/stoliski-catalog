/* Share tracking → Google Sheet (Apps Script web app, see build/tracking-apps-script.gs).
   Records only: event, apartment, agent name, link id. No customer details, no IP. */
const TRACK_URL = 'https://script.google.com/macros/s/AKfycbyrQ9fNvAsUmkV5SerUPSyH5RXGcno92a1lTph71U0jvg7TjS5LgPHGLR8xNvDwcWfv/exec'; // paste the Apps Script "Web app URL" here; empty = tracking off

function track(event, data){
  if(!TRACK_URL) return;
  const body = JSON.stringify(Object.assign({event, page: location.pathname.split('/').pop()||'index.html'}, data));
  try{
    if(navigator.sendBeacon && navigator.sendBeacon(TRACK_URL, new Blob([body],{type:'text/plain'}))) return;
  }catch(e){}
  try{ fetch(TRACK_URL,{method:'POST',mode:'no-cors',body,keepalive:true}); }catch(e){}
}

// short random id that ties a sent link to its later opens
function newLinkId(){ return Math.random().toString(36).slice(2,8); }
