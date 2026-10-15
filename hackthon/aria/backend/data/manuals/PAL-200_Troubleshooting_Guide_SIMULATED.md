# PAL-200 Robotic Palletizing Cell — Maintenance and Troubleshooting Guide (SIMULATED)

This is a simulated document created for the ARIA hackathon prototype. It describes the fictional PAL-200 palletizing cell used by the simulator. Do not use it for real equipment.

## 1 Safety rules for troubleshooting

All troubleshooting that requires entering the cell, touching the gripper, cleaning sensors or working at the pallet station must be performed by an authorized maintenance technician under the site lockout/tagout procedure.

Remote software diagnostics are read-only unless a procedure explicitly allows a maintenance-mode test. Software tools must never restart the cell, reset safety circuits, bypass interlocks, mute light curtains or force PLC outputs.

Restarting the cell after a fault is performed by an authorized operator at the HMI only after the cause has been removed and the cell area is confirmed clear.

## 2 Sequence overview

The cell runs a fixed sequence controlled by the PLC.

Step 10 WAIT_CASE: the robot waits at home until photo-eye B12 confirms a case at the pick stop.
Step 20 MOVE_TO_PICK: the robot moves over the case.
Step 30 GRIP_CLOSE: output Q4.0 energizes valve Y4. The gripper closed sensor B21 (input I2.1) must switch on within 1.5 s, otherwise alarm A-301 is raised.
Step 40 PLACE: the robot places the case. Place requires pallet located (I6.1), light curtain LC2 OSSD healthy and safety relay K20 closed.
Step 50 RELEASE: valve Y4 de-energizes and open sensor B20 (I2.0) must switch on.

## 3 Alarm reference

### A-301 Gripper close not confirmed

Meaning: the close command Q4.0 was on but closed sensor B21 did not switch on within the 1.5 s confirmation window.

Common causes, in order of field frequency:
1. Closed sensor B21 misaligned or out of range, especially after gripper finger replacement.
2. Air pressure at the gripper manifold below 5.5 bar, causing a slow close. The main pressure switch only trips below 4.0 bar, so low-but-not-critical pressure does not raise its own alarm.
3. Loose or damaged B21 cable or M8 connector (IO-Link communication drop-outs).
4. Valve Y4 coil or output failure (gripper does not move, open sensor B20 stays on).
5. Mechanical obstruction of the jaws.

Recommended diagnostic order: read B21 IO-Link distance, check Y4 coil current with Q4.0 on, read manifold pressure. A manual open/close cycle may only be run in maintenance mode with the robot at home.

### A-210 Case not detected at pick position

Meaning: the sequence waited 20 s at step 10 without B12 detecting a case.

Common causes:
1. Photo-eye B12 lens contaminated by cardboard dust (received-light margin below 60 %).
2. Line starvation: no cases arriving from the upstream case erector (entry sensor B10 count is zero).
3. Case jammed on the infeed guides (conveyor motor load above 80 %).
4. Infeed conveyor drive stopped or faulted.

If entry sensor B10 counts cases but none are detected at the pick stop after the expected 9 s transit time, the problem is between the infeed entry and B12.

### S-120 Light curtain LC2 interrupted and W-450 place permissive missing

Meaning: the pallet-exit light curtain LC2 has switched its OSSD outputs off. The sequence holds at step 40 PLACE and W-450 is raised after 30 s.

Common causes:
1. Partial obstruction of some beams, typically a loose stretch-film tail or debris. Beam diagnostics show a contiguous group of beams interrupted while the others are strong.
2. Emitter/receiver misalignment, for example after forklift contact. All beams show weak signal.
3. LC2 clear but safety relay K20 latched and waiting for a manual reset.
4. LC2 internal device fault (fault code shown in diagnostics).

LC2 and K20 are part of the safety function. They are reset only locally by an authorized person after physically inspecting the zone.

## 4 Procedures

### 4.1 Closed sensor B21 alignment check

1. Lock out the cell and isolate air to the gripper.
2. Close the jaws manually with the maintenance valve and confirm they reach the end stop.
3. Read the B21 measured distance over IO-Link or with a feeler gauge. The switching distance is 2.0 mm; set the gap to 1.0 mm ± 0.2 mm.
4. Torque the bracket screws to 4 Nm. A keyed bracket (part 4471-KB) prevents the sensor shifting during finger changes.
5. Restore air, remove lockout and run 20 test cycles in maintenance mode before returning to production.

After any gripper finger replacement, perform this check before releasing the cell.

### 4.2 Gripper air supply check

1. Read the manifold pressure transducer. Normal operating range is 6.0 to 6.5 bar; the minimum for the rated 0.7 s close time is 5.5 bar.
2. If the manifold pressure is low, check the plant air header pressure at the cell drop. If the header is also low, contact the utilities team; the cause is upstream of the cell.
3. If the header is normal but the manifold is low, inspect the cell filter-regulator and replace a blocked filter element.

### 4.3 Photo-eye B12 cleaning

1. Stop the infeed conveyor and lock out.
2. Clean the B12 lens and reflector with a lint-free cloth. Do not use solvents.
3. Check the received-light margin over IO-Link. A margin above 120 % is acceptable; below 60 % the contamination warning is set.
4. Add or confirm weekly lens cleaning in the preventive maintenance plan.

### 4.4 Light curtain LC2 inspection and reset

1. Only an authorized person may perform this procedure.
2. Stop the cell and apply lockout at the pallet station before entering the zone.
3. Inspect the protective field for film, debris or misplaced objects. Remove any obstruction.
4. Check emitter and receiver alignment indicators. If all beams are weak, perform realignment and a safety function test.
5. Leave the zone, remove lockout and perform the local K20 reset at the reset push-button outside the protective field.
6. Confirm OSSD outputs are on before the operator restarts the cell.

### 4.5 Restart after a fault

1. Confirm the root cause has been removed and documented.
2. Confirm nobody is inside the cell.
3. Acknowledge the alarm at the HMI and restart in AUTO. Restart is an operator action; it is not performed by remote software.
