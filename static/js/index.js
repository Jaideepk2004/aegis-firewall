/* ════════════════════════════════════════════
   BACKGROUND STARS
════════════════════════════════════════════ */
(function(){
  const canvas = document.getElementById('bg-canvas');
  const ctx = canvas.getContext('2d');
  function resize(){ canvas.width=innerWidth; canvas.height=innerHeight; }
  resize(); window.addEventListener('resize', resize);

  const stars = Array.from({length:180}, ()=>({
    x: Math.random()*innerWidth,
    y: Math.random()*innerHeight,
    r: Math.random()*1.2+0.2,
    phase: Math.random()*Math.PI*2,
    speed: Math.random()*0.4+0.15,
    teal: Math.random()
  }));

  let t=0;
  function draw(){
    const W=canvas.width, H=canvas.height;
    ctx.clearRect(0,0,W,H);
    t+=0.008;
    const gx=W*0.5, gy=H*0.45;
    const grad=ctx.createRadialGradient(gx,gy,0,gx,gy,W*0.38);
    grad.addColorStop(0,'rgba(0,220,120,0.04)');
    grad.addColorStop(0.5,'rgba(0,180,80,0.02)');
    grad.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=grad; ctx.fillRect(0,0,W,H);
    stars.forEach(s=>{
      const alpha=0.07+(Math.sin(t*s.speed+s.phase)*0.5+0.5)*0.25;
      const r2=Math.round(s.teal*0+(1-s.teal)*91);
      const g2=Math.round(s.teal*200+(1-s.teal)*196);
      const b2=Math.round(s.teal*150+(1-s.teal)*1);
      ctx.beginPath(); ctx.arc(s.x,s.y,s.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(${r2},${g2},${b2},${alpha})`; ctx.fill();
    });
    requestAnimationFrame(draw);
  }
  draw();
})();

/* ════════════════════════════════════════════
   HERO — THREE.JS SHIELD PARTICLE SYSTEM v5
════════════════════════════════════════════ */
(function(){
  const canvas   = document.getElementById('hero-canvas');
  const renderer = new THREE.WebGLRenderer({canvas, alpha:true, antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

  const scene  = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000);
  camera.position.set(0, 0, 24);

  function resize(){
    const W = canvas.parentElement.clientWidth;
    const H = canvas.parentElement.clientHeight;
    renderer.setSize(W, H);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize);

const SV = [
  [-6.5,7.5], [-4,7.2], [-2,7.8], [0,8.8], [2,7.8], [4,7.2], [6.5,7.5],

  [6.7,6.2], [7.0,4.5], [7.1,2.5], [7.0,0], [6.5,-2.5], [5.5,-5],

  [3.5,-8], [0,-11.5], [-3.5,-8],

  [-5.5,-5], [-6.5,-2.5], [-7.0,0], [-7.1,2.5], [-7.0,4.5], [-6.7,6.2],

  [-6.5,7.5]
];

  const svVec3   = SV.map(p => new THREE.Vector3(p[0], p[1], 0));
  const curve    = new THREE.CatmullRomCurve3(svVec3, true, 'catmullrom', 0.2);
  const outPts3  = curve.getPoints(600);

  function insideShield(px, py){
    if(py > 9.9 || py < -11.0 || Math.abs(px) > 9.2) return false;
    let inside = false;
    for(let i=0, j=SV.length-1; i<SV.length; j=i++){
      const xi=SV[i][0], yi=SV[i][1], xj=SV[j][0], yj=SV[j][1];
      if(((yi>py)!==(yj>py))&&(px<(xj-xi)*(py-yi)/(yj-yi)+xi))
        inside = !inside;
    }
    return inside;
  }

  function inKeyhole(px, py){
    const dx=px, dy=py-0.8;
    if(Math.sqrt(dx*dx+dy*dy) < 1.6) return true;
    if(Math.abs(px) < 0.6 && py < 0.8 && py > -2.5) return true;
    return false;
  }

  const N       = 40000;
  const restPos  = new Float32Array(N*3);
  const burstPos = new Float32Array(N*3);
  const positions= new Float32Array(N*3);
  const colors   = new Float32Array(N*3);

  let filled=0, tries=0;
  while(filled < N && tries < N*8){
    tries++;
    const px = (Math.random()-0.5)*20;
    const py = (Math.random()-0.5)*24;
    if(!insideShield(px,py)) continue;
    if(inKeyhole(px,py))     continue;

    const nx = px/9.0, ny = py/10.8;
    const dome = Math.max(0, 1 - nx*nx*0.9 - ny*ny*0.75) * 1.1;
    const z    = dome + (Math.random()-0.5)*0.18;

    restPos[filled*3]  =px; restPos[filled*3+1]=py; restPos[filled*3+2]=z;

    const bAngle = Math.random()*Math.PI*2;
    const bSpeed = 14 + Math.random()*28;
    burstPos[filled*3]   = px + Math.cos(bAngle)*bSpeed;
    burstPos[filled*3+1] = py + Math.sin(bAngle)*bSpeed*0.7 + Math.random()*8;
    burstPos[filled*3+2] = z  + (Math.random()-0.5)*18;

    positions[filled*3]=px; positions[filled*3+1]=py; positions[filled*3+2]=z;

    const edgeD  = Math.sqrt(nx*nx*0.88+ny*ny*0.82);
    const core   = Math.max(0, 1-edgeD);
    const lit    = Math.max(0, z)/1.2;
    const topF   = Math.max(0,(py+10.8)/21.6);
    const br     = 0.22 + core*0.62 + lit*0.16;

    colors[filled*3]   = 0;
    colors[filled*3+1] = Math.min(1, br*(0.78+topF*0.22));
    colors[filled*3+2] = Math.min(1, br*(0.32+core*0.48));
    filled++;
  }
  while(filled < N){
    restPos[filled*3]=0;  restPos[filled*3+1]=-60; restPos[filled*3+2]=0;
    burstPos[filled*3]=0; burstPos[filled*3+1]=-60; burstPos[filled*3+2]=0;
    positions[filled*3]=0;positions[filled*3+1]=-60;positions[filled*3+2]=0;
    colors[filled*3]=0; colors[filled*3+1]=0.04; colors[filled*3+2]=0.02;
    filled++;
  }

  const geo    = new THREE.BufferGeometry();
  const posAttr= new THREE.BufferAttribute(positions,3);
  posAttr.setUsage(THREE.DynamicDrawUsage);
  geo.setAttribute('position', posAttr);
  geo.setAttribute('color',    new THREE.BufferAttribute(colors,3));

  const mat = new THREE.PointsMaterial({
    size:0.12, vertexColors:true, transparent:true, opacity:0,
    sizeAttenuation:true, depthWrite:false,
    blending: THREE.AdditiveBlending
  });
  const shieldPts = new THREE.Points(geo, mat);

  const outGeo  = new THREE.BufferGeometry().setFromPoints(outPts3);
  const outMat  = new THREE.LineBasicMaterial({
    color:0x00ffcc, transparent:true, opacity:0, blending:THREE.AdditiveBlending
  });
  const outLine = new THREE.Line(outGeo, outMat);

  const inPts3 = outPts3.map(p=>new THREE.Vector3(p.x*0.89, p.y*0.89, -0.15));
  const inGeo  = new THREE.BufferGeometry().setFromPoints(inPts3);
  const inMat  = new THREE.LineBasicMaterial({
    color:0x00aa88, transparent:true, opacity:0, blending:THREE.AdditiveBlending
  });
  const inLine = new THREE.Line(inGeo, inMat);

  const group = new THREE.Group();
  group.add(shieldPts, outLine, inLine);
  group.rotation.x = -0.07;
  scene.add(group);

  const glowMat = new THREE.MeshBasicMaterial({
    color:0x00ff88, transparent:true, opacity:0,
    blending:THREE.AdditiveBlending, depthWrite:false, side:THREE.DoubleSide
  });
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(22,26), glowMat);
  glow.position.z = -5;
  scene.add(glow);

  let mxN=0, myN=0;
  document.addEventListener('mousemove', e=>{
    mxN=(e.clientX/innerWidth -0.5)*2;
    myN=-(e.clientY/innerHeight-0.5)*2;
  });

  let scrollTarget=0, scrollSmooth=0;
  window.addEventListener('scroll', ()=>{
    const hero  = document.getElementById('section-hero');
    const rect  = hero.getBoundingClientRect();
    const total = hero.offsetHeight - innerHeight;
    scrollTarget = Math.max(0, Math.min(1, -rect.top/total));
  });

  let t=0;
  function easeOut3(x){ return 1 - Math.pow(1-x, 3); }

  function animate(){
    requestAnimationFrame(animate);
    t += 0.005;

    scrollSmooth += (scrollTarget - scrollSmooth)*0.07;
    const sp = easeOut3(Math.min(1, scrollSmooth));

    const pa = posAttr.array;
    for(let i=0; i<N; i++){
      const i3=i*3;
      const wobble = sp<0.03 ? Math.sin(t*1.3+i*0.0031)*0.012 : 0;
      pa[i3]  = restPos[i3]   + (burstPos[i3]  -restPos[i3]  )*sp + wobble;
      pa[i3+1]= restPos[i3+1] + (burstPos[i3+1]-restPos[i3+1])*sp;
      pa[i3+2]= restPos[i3+2] + (burstPos[i3+2]-restPos[i3+2])*sp;
    }
    posAttr.needsUpdate = true;

    outMat.opacity = 0.72*(1 - Math.min(1, sp*1.8));
    inMat.opacity  = 0.25*(1 - Math.min(1, sp*2.2));

    group.rotation.y = t*0.3 + mxN*0.13;
    group.rotation.x = -0.07  + myN*0.07;

    glowMat.opacity = (0.022+Math.sin(t*0.5)*0.007)*(1-sp);

    const hl=document.getElementById('hero-left');
    const hr=document.getElementById('hero-right');
    if(hl) hl.style.opacity=Math.max(0,1-scrollSmooth*3);
    if(hr) hr.style.opacity=Math.max(0,1-scrollSmooth*3);

    renderer.render(scene, camera);
  }
  animate();

  gsap.to(mat,    {opacity:0.88, duration:2.2, ease:'power2.out', delay:0.4});
  gsap.to(outMat, {opacity:0.72, duration:1.5, ease:'power2.out', delay:1.1});
  gsap.to(inMat,  {opacity:0.25, duration:1.5, ease:'power2.out', delay:1.3});
  gsap.to(glowMat,{opacity:0.022,duration:2.0, ease:'power2.out', delay:0.9});
  gsap.from(group.scale,{x:0.04,y:0.04,z:0.04,duration:2.5,ease:'elastic.out(1,0.5)',delay:0.4});
})();

/* ════════════════════════════════════════════
   SERVICE CARD CENTER — PARTICLE CANVAS
════════════════════════════════════════════ */
(function(){
  const canvas = document.getElementById('card-canvas-2');
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  function resize(){ canvas.width=canvas.parentElement.clientWidth; canvas.height=canvas.parentElement.clientHeight; }
  resize(); window.addEventListener('resize', resize);

  const pts = Array.from({length:60},()=>({
    x: Math.random()*500, y: Math.random()*500,
    vx: (Math.random()-.5)*0.4, vy: (Math.random()-.5)*0.4,
    r: Math.random()*2+1
  }));

  function draw(){
    const W=canvas.width, H=canvas.height;
    ctx.clearRect(0,0,W,H);
    pts.forEach(p=>{ p.x+=p.vx; p.y+=p.vy; if(p.x<0||p.x>W)p.vx*=-1; if(p.y<0||p.y>H)p.vy*=-1; });
    pts.forEach((a,i)=>{
      pts.slice(i+1).forEach(b=>{
        const d=Math.hypot(a.x-b.x,a.y-b.y);
        if(d<100){ ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.strokeStyle=`rgba(91,196,1,${(1-d/100)*0.15})`; ctx.lineWidth=.5; ctx.stroke(); }
      });
      ctx.beginPath(); ctx.arc(a.x,a.y,a.r,0,Math.PI*2);
      ctx.fillStyle='rgba(91,196,1,0.4)'; ctx.fill();
    });
    requestAnimationFrame(draw);
  }
  draw();
})();

/* ════════════════════════════════════════════
   CONTACT CANVAS — HOURGLASS BUBBLE EFFECT
════════════════════════════════════════════ */
(function(){
  const canvas = document.getElementById('contact-canvas');
  if(!canvas) return;

  const renderer = new THREE.WebGLRenderer({canvas, alpha:true, antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 1000);
  camera.position.set(0,0,25);

  function resize(){
    const sec = document.getElementById('section-contact');
    const W=sec.clientWidth, H=sec.clientHeight||innerHeight;
    renderer.setSize(W,H); camera.aspect=W/H; camera.updateProjectionMatrix();
    canvas.style.width=W+'px'; canvas.style.height=H+'px';
  }
  resize(); window.addEventListener('resize', resize);

  const M = 6000;
  const cPos = new Float32Array(M*3);
  const cCol = new Float32Array(M*3);

  for(let i=0;i<M;i++){
    const t = (Math.random()-0.5)*2;
    const radius = Math.abs(t)*8 + 0.5;
    const angle = Math.random()*Math.PI*2;
    const jitter = (Math.random()-0.5)*1.5;
    cPos[i*3] = Math.cos(angle)*radius + jitter;
    cPos[i*3+1] = t*9;
    cPos[i*3+2] = Math.sin(angle)*radius + jitter;
    const g = 0.6+Math.abs(t)*0.4;
    const b = Math.abs(t)*0.4;
    cCol[i*3]=0; cCol[i*3+1]=g; cCol[i*3+2]=b;
  }

  const cGeo = new THREE.BufferGeometry();
  cGeo.setAttribute('position', new THREE.BufferAttribute(cPos,3));
  cGeo.setAttribute('color', new THREE.BufferAttribute(cCol,3));
  const cMat = new THREE.PointsMaterial({size:0.1, vertexColors:true, transparent:true, opacity:0.85, sizeAttenuation:true});
  scene.add(new THREE.Points(cGeo, cMat));

  const glowGeo = new THREE.SphereGeometry(2,32,32);
  const glowMat = new THREE.MeshBasicMaterial({color:0x00ffcc, transparent:true, opacity:0.08});
  scene.add(new THREE.Mesh(glowGeo, glowMat));

  let ct=0, cmxN=0, cmyN=0;
  document.addEventListener('mousemove',e=>{ cmxN=(e.clientX/innerWidth-0.5)*2; cmyN=-(e.clientY/innerHeight-0.5)*2; });

  const contactCloud = scene.children[0];
  function animContact(){
    requestAnimationFrame(animContact);
    ct+=0.006;
    if(contactCloud){ contactCloud.rotation.y=ct*0.15+cmxN*0.2; contactCloud.rotation.z=Math.sin(ct*0.3)*0.05; }
    renderer.render(scene,camera);
  }
  animContact();
})();

/* ── PRELOADER ───────────────────────────────────── */
(function(){
  const fill=document.getElementById('plf'),pctEl=document.getElementById('plp'),pl=document.getElementById('pl');
  let p=0;
  const t=setInterval(()=>{
    p+=Math.random()*13+5; if(p>100)p=100;
    fill.style.transform=`translateX(${-(100-p).toFixed(1)}%)`;
    pctEl.textContent=Math.floor(p);
    if(p>=100){clearInterval(t);setTimeout(()=>gsap.to(pl,{opacity:0,duration:.85,ease:'power2.inOut',onComplete:()=>{pl.style.display='none';boot();}}),280);}
  },50);
})();

/* ════════════════════════════════════════════
   GSAP SCROLL ANIMATIONS
════════════════════════════════════════════ */
gsap.registerPlugin(ScrollTrigger);

function boot(){
document.querySelectorAll('.fade-up').forEach((el,i)=>{
  gsap.to(el, {
    opacity:1, y:0, duration:0.9, ease:'power3.out',
    scrollTrigger:{ trigger:el, start:'top 88%', toggleActions:'play none none none' }
  });
});

gsap.from('#hero-left', { x:-60, opacity:0, duration:1.2, ease:'power3.out', delay:0.5 });
gsap.from('#hero-right', { x:60, opacity:0, duration:1.2, ease:'power3.out', delay:0.7 });
gsap.from('.scroll-cta', { opacity:0, y:20, duration:1, ease:'power3.out', delay:1.2 });

const sections = ['#section-hero','#section-services-detail','#section-about'];
const navLinks = document.querySelectorAll('#bottom-nav .nav-item');
sections.forEach((id, idx)=>{
  ScrollTrigger.create({
    trigger: id,
    start:'top center',
    end:'bottom center',
    onEnter(){ navLinks.forEach(l=>l.classList.remove('active')); if(navLinks[idx]) navLinks[idx].classList.add('active'); },
    onEnterBack(){ navLinks.forEach(l=>l.classList.remove('active')); if(navLinks[idx]) navLinks[idx].classList.add('active'); }
  });
});
}