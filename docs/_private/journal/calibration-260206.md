*These notes document the sidekick calibration branch where I worked on understanding better the forward kinematics and how the equations could be optimized for better positioning over the 96 well plate. The end result was improved (but not ideal) positioning through the use of an error minimization routine that used the steps and origin offset as adjustable parameters. The assumption made here is that the end stops do not accurately represent 0 and 1600 steps for m1 and m2, respectively. The addition of this fixed step offset seems to have improved things. At some point, a rotation in addition to translation might be needed. However, to do this, a better data collection approach will be needed by comparing the actual and predicted positions. Perhaps using a pump in the center of the end effector and depositing a single drop at a position might provide useful information.*

Completed some housecleaning (removed calibration routines) and started improved transect data collection that includes multi-channel data collection and visualization. Next step is either (a) create a more complete template with multiple spots for analysis or (b) continue using filled wells. Either way must result in a method that can be implemented to improve IK. See chat `[!] Calibrate Arm Using Numerical Optimization` for some strategies.

Working on sidekick calibration. joint_cross_search seems to be good at finding a minimum to pinpoint the center of a well, but using this information in a calibration is problematic. Next step is to try different calibration methods, possibly with a template that has a few more data points.

Six point data collection providing the predicted and actual steps

|well|m1_pred|m2_pred|m1_act|m2_act|
|----|-------|-------|------|------|
|A1  |335    |887    |366   |892   |
|H1  |131    |1178   |137   |1171  |
|C5  |552    |1113   |564   |1116  |
|F8  |546    |1308   |543   |1306  |
|A12 |987    |1486   |971   |1469  |
|H12 |518    |1516   |501   |1510  |

Mathematica code to convert angles to coordinates
```
pt[t1_, t2_, l1_, l3_] := Module[{x, y},
  x = l1 Cos[t1 Degree] - l3 Cos[t2 Degree];
  y = l1 Sin[t1 Degree] - l3 Sin[t2 Degree];
  {x, y}
  ]
```
And converting steps to angles is multiplying by 0.9 (step angle degrees) and diviging by 8 (microsteps)

Analysis of these data with step_analysis.py reveals that the m1 home is actually at -33, the m2 home is at 1610, and there is an effective axis separation of 5.607 mm. I'm skeptical about the axis separation, especially one that big. Time to try implementing that.

Several days later, two points coincide with above table (one was exact, the other differed by 1 step in one dimension). More exploration of forward kinematics using [this website](https://orenanderson.com/five-bar-robotics-kinematics-and-dynamics/) as a resource. Mathematica code stored in temp (5-bar-forward-kinematics.nb). 

Using mathematica to fit the forward kinetics equation with predicted (robot) cartesian coordinates and actual (well plate - A1 -> 0,0) coordinates using a translation offset and step offset seems to have created an improved calibration.

Additional optimization in calibration is needed. However, the four corner wells can be reached by each of the pumps. This might be good enough for now.


Mathematica code used to describe forward kinematics and the optimization.
```
(*link-center points*)
xyl[q1_, a1_] := {a1 Cos[q1], a1 Sin[q1]}
xyr[q2_, a2_, c_] := {c + a2 Cos[q2], a2 Sin[q2]}

(*deltas and distance between centers*)
dxdy[q1_, q2_, a1_, a2_, c_] := xyr[q2, a2, c] - xyl[q1, a1]
dist[q1_, q2_, a1_, a2_, c_] := 
 Module[{dx, dy}, {dx, dy} = dxdy[q1, q2, a1, a2, c];
  Sqrt[dx^2 + dy^2]]

(*scalars a and h*)
asc[q1_, q2_, a1_, a2_, a3_, a4_, c_] := 
 Module[{d = dist[q1, q2, a1, a2, c]}, (a3^2 - a4^2 + d^2)/(2 d)]
hsc[q1_, q2_, a1_, a2_, a3_, a4_, c_] := 
 Module[{a = asc[q1, q2, a1, a2, a3, a4, c]}, Sqrt[Max[0, a3^2 - a^2]]]

(*base point on the line of centers*)
xbase[q1_, q2_, a1_, a2_, a3_, a4_, c_] := 
 Module[{xl, dx, d, a}, 
  xl = xyl[q1, a1]; {dx, d} = {dxdy[q1, q2, a1, a2, c][[1]], 
    dist[q1, q2, a1, a2, c]};
  a = asc[q1, q2, a1, a2, a3, a4, c];
  xl[[1]] + (a/d) dx]
ybase[q1_, q2_, a1_, a2_, a3_, a4_, c_] := 
 Module[{yl, dy, d, a}, 
  yl = xyl[q1, a1]; {dy, d} = {dxdy[q1, q2, a1, a2, c][[2]], 
    dist[q1, q2, a1, a2, c]};
  a = asc[q1, q2, a1, a2, a3, a4, c];
  yl[[2]] + (a/d) dy]

(*forward kinematics:returns {xd,yd};s=\
\[PlusMinus]1 selects assembly mode*)
FK[q1_, q2_, a1_, a2_, a3_, a4_, c_, s_ : 1] := 
 Module[{dx, dy, d, xb, yb, h}, {dx, dy} = dxdy[q1, q2, a1, a2, c];
  d = dist[q1, q2, a1, a2, c];
  xb = xbase[q1, q2, a1, a2, a3, a4, c];
  yb = ybase[q1, q2, a1, a2, a3, a4, c];
  h = hsc[q1, q2, a1, a2, a3, a4, c];
  If[d == 0, Return[$Failed]];(*degenerate*){xb - s (h/d) dy, 
   yb + s (h/d) dx}]

(*forward kinematics with end effector*)
pred[m1_, m2_] := 
 FK[m1 Pi/1600, m2 Pi/1600, 7, 3, 3, 7, 0, -1] - 
   13 {Cos[m2 Pi/1600], Sin[m2 Pi/1600]} // N
pred[366, 892]

model[m1_, m2_] := {xoffset, yoffset} + 
  FK[(m1 + m1e) Pi/1600, (m2 + m2e) Pi/1600, 7, 3, 3, 7, 
   0, -1] - (13) {Cos[(m2 + m2e) Pi/1600], Sin[(m2 + m2e) Pi/1600]}
obs = MapThread[
   pred, {{366, 137, 564, 543, 971, 501}, {892, 1171, 1116, 1306, 
     1469, 1510}}];
actual = {{0, 0}, {6.3, 0}, {1.8, 3.6}, {4.5, 6.3}, {0, 9.9}, {6.3, 
    9.9}};

(* error function is the sum of the square of the differences, \
adding the results of x and y at each point *)
Total  [(#[[1]]^2 + #[[2]]^2) & /@ (actual - obs)]

(* optimization routing *)
FindMinimum[Total [(#[[1]]^2 + #[[2]]^2) & /@ (actual - 
     MapThread[
      model, {{366, 137, 564, 543, 971, 501}, {892, 1171, 1116, 1306, 
        1469, 1510}}]
    )], {{xoffset, -7}, {yoffset, 5}, {m1e, 2}, {m2e, 25}}]
