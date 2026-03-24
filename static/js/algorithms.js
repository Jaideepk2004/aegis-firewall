/* BACKGROUND — GREEN PARTICLE NETWORK (visible but not overpowering) */
(function(){
  const canvas = document.getElementById('bg-canvas');
  const ctx = canvas.getContext('2d');

  function resize(){
    canvas.width = innerWidth;
    canvas.height = innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const COUNT = 90;

  const particles = Array.from({ length: COUNT }, () => ({
    x:     Math.random() * innerWidth,
    y:     Math.random() * innerHeight,
    vx:    (Math.random() - 0.5) * 0.35,
    vy:    (Math.random() - 0.5) * 0.35,
    r:     Math.random() * 1.5 + 0.8,
    pulse: Math.random() * Math.PI * 2,
    speed: Math.random() * 0.3 + 0.15
  }));

  let t = 0;
  const CONNECT_DIST = 130;

  function draw() {
    requestAnimationFrame(draw);
    t += 0.008;
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    /* move particles */
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
    });

    /* draw connections */
    for (let i = 0; i < COUNT; i++) {
      for (let j = i + 1; j < COUNT; j++) {
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist < CONNECT_DIST) {
          const alpha = (1 - dist / CONNECT_DIST) * 0.10;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(91,196,1,${alpha})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }
    }

    /* draw dots */
    particles.forEach(p => {
      const pulse = 0.5 + Math.sin(t * p.speed + p.pulse) * 0.5;
      const alpha  = 0.15 + pulse * 0.15;
      const radius = p.r + pulse * 0.4;

      ctx.beginPath();
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(91,196,1,${alpha})`;
      ctx.fill();
    });
  }
  draw();
})();

/* PRELOADER */
(function(){
  const fill=document.getElementById('plf'),pctEl=document.getElementById('plp'),pl=document.getElementById('pl');
  let p=0;
  const t=setInterval(()=>{
    p+=Math.random()*13+5; if(p>100)p=100;
    fill.style.transform=`translateX(${-(100-p).toFixed(1)}%)`;
    pctEl.textContent=Math.floor(p);
    if(p>=100){
      clearInterval(t);
      setTimeout(()=>{
        gsap.to(pl,{opacity:0,duration:.85,ease:'power2.inOut',onComplete:()=>{
          pl.style.display='none';
          boot();
        }});
      },280);
    }
  },50);
})();

/* GSAP SCROLL ANIMATIONS */
gsap.registerPlugin(ScrollTrigger);

function boot(){
  /* Smooth scroll for nav dropdown links on this page */
  document.querySelectorAll('.scroll-to').forEach(link => {
    link.addEventListener('click', function(e) {
      const target = document.getElementById(this.dataset.target);
      if (target) {
        e.preventDefault();
        const offset = 80; /* header height clearance */
        const top = target.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    });
  });
  document.querySelectorAll('.fade-up').forEach((el)=>{
    gsap.to(el,{
      opacity:1, y:0, duration:0.9, ease:'power3.out',
      scrollTrigger:{ trigger:el, start:'top 88%', toggleActions:'play none none none' }
    });
  });

  /* Hero fade in */
  gsap.to('.page-hero h1',  {opacity:1, y:0, duration:1.2, ease:'power3.out', delay:0.3});
  gsap.to('.page-hero .page-hero-sub', {opacity:1, y:0, duration:1.0, ease:'power3.out', delay:0.5});

  /* Active nav highlight by section */
  const sections = ['#qlearning','#dqn','#ppo'];
  const navLinks = document.querySelectorAll('#bottom-nav .nav-dropdown-menu a');
  sections.forEach((id,idx)=>{
    ScrollTrigger.create({
      trigger: id,
      start:'top center', end:'bottom center',
      onEnter(){ navLinks.forEach(l=>l.style.color=''); if(navLinks[idx]) navLinks[idx].style.color='var(--green)'; },
      onEnterBack(){ navLinks.forEach(l=>l.style.color=''); if(navLinks[idx]) navLinks[idx].style.color='var(--green)'; }
    });
  });
}