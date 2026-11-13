# TASK: pseudo-3D racer (OutRun style)
FILE=C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\racer\racer.py
Stdlib only; run with `py` (3.14). No pygame/pip. Quote paths.

## Constants
W,H=640,480 FPS=30 STEP=1/FPS SEG=200 RUMBLE=3 ROAD_W=2000 CAM_H=1000
CAM_D=1/math.tan(math.radians(50)) DRAW=150 PLAYER_Z=CAM_H*CAM_D
MAX=SEG/STEP ACCEL=MAX/5 BRAKE=-MAX DECEL=-MAX/5 OFF_DECEL=-MAX/2 OFF_LIMIT=MAX/4 CENTRIF=0.3 N_CARS=20
Colors: sky #72D7EE grass #10AA10/#009A00 road #6B6B6B/#696969 rumble #FFFFFF/#C00000 lane #CCCCCC

## Pure functions (module level, no tkinter)
- project(x,y,z,cx,cy,cz): None if z-cz<=0; s=CAM_D/(z-cz); return (W/2+s*(x-cx)*W/2, H/2-s*(y-cy)*H/2, s*ROAD_W*W/2, s)
- ease_in(a,b,p)=a+(b-a)*p**2; ease_in_out(a,b,p)=a+(b-a)*(0.5-math.cos(p*math.pi)/2)
- add_road(t,enter,hold,leave,curve): curve eases 0->curve, holds, eases ->0
- build_track(): dicts index,z1=i*SEG,z2=z1+SEG,curve,dark=(i//RUMBLE)%2==1; straight, curves +-2,+-4,+-6, straight; 400-600 segs
- track_length(t)=len(t)*SEG; find_segment(t,z)=t[int(z//SEG)%len(t)]
- increase(v,inc,m): v+inc wrapped into [0,m)
- overlap(x1,w1,x2,w2): spans overlap
- new_state(): position=0 speed=0 x=0 lap=1 lap_time=0 last_lap=None best_lap=None
- update_player(s,dt,keys,t), keys subset of left/right/up/down:
  seg=find_segment(t,pos+PLAYER_Z); p=speed/MAX; dx=dt*2*p; left x-=dx; right x+=dx
  x-=dx*p*seg["curve"]*CENTRIF; speed+=ACCEL*dt if up, BRAKE*dt if down, else DECEL*dt
  if abs(x)>1 and speed>OFF_LIMIT: speed+=OFF_DECEL*dt; clamp x[-2,2] speed[0,MAX]
  old=pos; pos=increase(pos,dt*speed,L); lap_time+=dt
  if pos<old: last_lap=lap_time; best_lap=min; lap+=1; lap_time=0
- make_cars(t): N_CARS of z random, offset in (-0.8,0,0.8), speed MAX/4..MAX/2
- update_cars(cars,dt,t): z=increase(z,dt*speed,L)
- check_collisions(s,cars,t): hit if 0<=(z-pos-PLAYER_Z)%L<SEG and overlap(x,.3,offset,.3): speed=car speed*.5, pos just behind car; return bool

## GUI (import tkinter only inside main)
Canvas WxH; keys set via KeyPress/KeyRelease; root.after(1000//FPS,tick): update all, render.
render: delete all; sky + mountain polygon shifted by curve. Road: from find_segment(t,pos), DRAW segs, wrapped z+=L. xc=dxc=0, maxy=H. Per seg: project z1,z2 with cx=x*ROAD_W-xc (world units), cy=CAM_H, cz=pos; then xc+=dxc; dxc+=curve. Skip if None or sy2>=maxy; else maxy=sy2.
Draw grass rect sy2..sy1, rumble (w*1.15), road, lanes on light segs: create_polygon(x1-w1,y1,x1+w1,y1,x2+w2,y2,x2-w2,y2,fill=c,outline="").
Cars far->near: rect scaled by sw at sx+sw*offset. Player: red car at bottom, shifts when steering.
HUD: SPEED {int(speed/MAX*300)} km/h, LAP, TIME, LAST, BEST. Arrows drive; P pause (overlay lists keys); R restart; Esc quit.

## --selftest (no Tk): asserts, print SELFTEST OK, exit 0
1 project(0,0,1000,0,CAM_H,0) sx==W/2; z=4000: smaller sw, sy nearer H/2; z<=cz: None
2 increase(L-100,200,L)==100; increase(50,-100,L)==L-50
3 track has curve>0 and curve<0
4 30 steps up: 0<speed<=MAX; 10 steps down lowers it; straight 300-seg track, x=1.5, speed=MAX, 120 steps up: speed<=OFF_LIMIT+ACCEL*STEP
5 all-curve-4 track, speed=MAX/2, 1 step no keys: x<0
6 overlap(0,.3,.1,.3) True, overlap(-1,.3,1,.3) False; car just ahead same offset: collision True, speed drops
7 pos=L-10, speed=MAX, 1 step: lap==2, best_lap set

## Steps
1 run_command: py -c "import tkinter"
2 write_file FILE: constants, pure functions, selftest, line `# === GUI ===` (no GUI yet)
3 run_command: py -m py_compile "FILE", then py "FILE" --selftest until SELFTEST OK; fix with edit_file
4 edit_file: replace `# === GUI ===` with GUI + main(); redo step 3
5 verification_gate. Never run without --selftest. Finish: cd racer folder; py racer.py
