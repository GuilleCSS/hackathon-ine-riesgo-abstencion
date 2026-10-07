// Local visual QA with an isolated headless Edge profile; no personal browser data.
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const out=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(out,'../..');
const profile=path.join(root,'data','interim','dashboard_browser_profile');
await fs.mkdir(profile,{recursive:true});
const browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
  '--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking',
  '--remote-debugging-port=0',`--user-data-dir=${profile}`,'--window-size=1440,1000',
  '--use-angle=swiftshader','--enable-unsafe-swiftshader','about:blank'
],{windowsHide:true,stdio:['ignore','pipe','pipe']});
let stderr='';
browser.stderr.on('data',b=>{stderr+=b.toString();});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function waitFor(fn,timeout=90000){const end=Date.now()+timeout;while(Date.now()<end){const v=await fn();if(v)return v;await sleep(250);}throw new Error('Timeout waiting for browser condition');}
let ws,session;
const pending=new Map();let counter=0;const errors=[];
async function command(method,params={},page=true){return new Promise((resolve,reject)=>{const id=++counter;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(page&&session?{sessionId:session}:{})}));});}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value;}
async function text(){return evaluate('document.body?.innerText || ""');}
async function clickRect(rect){if(!rect||rect.width===0)throw new Error('Element is not visible');const x=rect.x+rect.width/2,y=rect.y+rect.height/2;await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});}
async function choose(label,option){
  const rect=await evaluate(`(()=>{const box=[...document.querySelectorAll('[data-testid="stSelectbox"]')].find(e=>e.innerText.startsWith(${JSON.stringify(label)}));const e=box?.querySelector('[role="combobox"]')||box;const r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null;})()`);
  await clickRect(rect);
  const target=await waitFor(()=>evaluate(`(()=>{const e=[...document.querySelectorAll('[role="option"]')].find(e=>e.innerText.toLowerCase().includes(${JSON.stringify(option.toLowerCase())}));const r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null;})()`),15000);
  await clickRect(target);
}
async function shot(name){const image=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(out,name),Buffer.from(image.data,'base64'));}
try{
  const endpoint=await waitFor(()=>stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1],20000);
  ws=new WebSocket(endpoint);
  await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
  ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);});
  const target=await command('Target.createTarget',{url:'about:blank'},false);
  session=(await command('Target.attachToTarget',{targetId:target.targetId,flatten:true},false)).sessionId;
  await command('Page.enable');await command('Runtime.enable');
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:'http://localhost:8501'});
  await waitFor(async()=> (await text()).includes('Modelo predictivo'));
  await choose('Modelo predictivo','Random Forest M17');
  await waitFor(async()=> (await text()).includes('Vista nacional simplificada'));
  await waitFor(()=>evaluate('document.querySelectorAll("canvas").length > 0'));
  await waitFor(()=>evaluate('!Array.from(document.querySelectorAll("button")).some(e=>e.innerText.trim()==="Stop")'));
  await sleep(15000);
  await evaluate('document.querySelector("[data-testid=stDeckGlJsonChart]")?.scrollIntoView({block:"center"})');
  await sleep(3000);
  await shot('VISTA_RF_NACIONAL.png');
  await choose('Entidad','aguascalientes');
  await waitFor(async()=> (await text()).includes('Polígonos de la selección'));
  await waitFor(()=>evaluate('!Array.from(document.querySelectorAll("button")).some(e=>e.innerText.trim()==="Stop")'));
  await sleep(3000);
  // Actual polygon picking: find an interior point of the largest source polygon.
  const raw=JSON.parse(await fs.readFile(path.join(root,'data/processed/rf_dashboard/boundaries_2027_entidad.geojson'),'utf8'));
  const g=raw.features.find(f=>f.properties.ID==='entidad:1').geometry;
  const polygons=g.type==='Polygon'?[g.coordinates]:g.coordinates;
  function area(r){let s=0;for(let i=0,j=r.length-1;i<r.length;j=i++)s+=r[j][0]*r[i][1]-r[i][0]*r[j][1];return Math.abs(s);}
  function inside(p,r){let hit=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const a=r[i],b=r[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])hit=!hit;}return hit;}
  const polygon=polygons.slice().sort((a,b)=>area(b[0])-area(a[0]))[0];
  const all=polygons.flat(2),xs=all.map(p=>p[0]),ys=all.map(p=>p[1]);
  const west=Math.min(...xs),east=Math.max(...xs),south=Math.min(...ys),north=Math.max(...ys);
  let point=null,score=-1;
  for(let i=1;i<25;i++)for(let j=1;j<25;j++){const p=[west+(east-west)*i/25,south+(north-south)*j/25];if(inside(p,polygon[0])&&!polygon.slice(1).some(r=>inside(p,r))){const d=Math.min(...polygon[0].map(q=>(q[0]-p[0])**2+(q[1]-p[1])**2));if(d>score){score=d;point=p;}}}
  if(!point)throw new Error('No polygon interior point found');
  const canvas=await evaluate('(()=>{const e=document.querySelector("[data-testid=stDeckGlJsonChart] canvas")||document.querySelector("canvas");const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})()');
  const zoom=Math.min(12,Math.max(3,Math.log2(360/Math.max(east-west,north-south,.01))-1));
  const size=512*2**zoom;
  const merc=p=>[size*(p[0]+180)/360,size*(.5-Math.log((1+Math.sin(p[1]*Math.PI/180))/(1-Math.sin(p[1]*Math.PI/180)))/(4*Math.PI))];
  const a=merc(point),b=merc([(west+east)/2,(south+north)/2]);
  const x=canvas.x+canvas.width/2+a[0]-b[0],y=canvas.y+canvas.height/2+a[1]-b[1];
  await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
  await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});
  await waitFor(async()=> (await text()).includes('Más datos del territorio'),20000);
  await shot('VISTA_RF_DETALLE.png');
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await sleep(1000);
  const collapse=await evaluate('(()=>{const sidebar=document.querySelector("[data-testid=stSidebar]");const candidates=[...sidebar.querySelectorAll("button")];const e=candidates.find(e=>/collapse|close|sidebar/i.test([e.getAttribute("aria-label"),e.title,e.getAttribute("data-testid")].join(" ")))||candidates[0];const r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null;})()');
  if(collapse)await clickRect(collapse);
  await sleep(1500);
  await shot('VISTA_RF_MOVIL.png');
  await fs.writeFile(path.join(out,'VERIFICACION_NAVEGADOR.txt'),`PASSED: actual Edge browser, isolated headless profile; national WebGL canvas; state filter; polygon click reveals details; desktop/mobile screenshots. Runtime exceptions: ${JSON.stringify(errors)}\n`);
  console.log('PASSED: actual browser map, filters, polygon picking and screenshots');
}catch(error){
  if(ws&&session){try{await shot('VISTA_RF_DIAGNOSTICO.png');}catch{}}
  await fs.writeFile(path.join(out,'DIAGNOSTICO_NAVEGADOR.txt'),String(error)+'\n'+JSON.stringify(errors));
  throw error;
}finally{
  if(ws?.readyState===1){try{await command('Browser.close',{},false);}catch{}ws.close();}
  browser.kill();
}
