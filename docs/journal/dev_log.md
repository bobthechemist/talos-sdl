# Dev Log

## [2026-01-28] Development documentation lacking

**Context**: Returning to the project after a one month(+) hiatus. Nothing in the documentation, git repository, or dev log provides meaningful information on where I was when the project was set aside.
**Issues**: There is a (re)learning curve to determine what was working and what wasn't. There is no resource such as a plan to refer to.
**Commentary**
- A plan would be nice to have. An end goal for the next stable version and then a series of projects to achieve that state.
- I'm creating some un-tracked files (CURRENT_STATUS and BRANCH_GOALS) to assist in documenting progress and tasks.
- I plan to branch three tasks: sidekick calibration, mcp implementation, agentic chat loop. The order is important: AI is useless if hardware is failing; MCP impelementation drives logic decisions in the agentic chat loop.

## [2025-11-12] Functional ai planner(?)

**Context**: Working towards AI operation of the sidekick so that it can generate a set of instructions from a human readable prompt
**Issues**: Three broad categories of challenges: the AI cannot do math, the AI doesn't remember the hardware state, the AI doesn't fully understand the effects of the commands
**Commentary**
- Original planning runs would occasionally remember that to_well has a pump argument which is necessary to run prior to dispense.
- Unrelated to the planner, there is still a calibration problem and A1 is not being reached properly when one of the pumps is requested. It appears that all pumps are going to the same (incorrect) location
- Related to ^^^ the AI is capable of correctly interpreting the prompt: "starting from well E6 ..."
- Deterministic python tools for doing chemistry math will be needed, but that is going to be a significant undertaking that requires some thought.  
- The current approach is to provide more information to the AI from the firmware itself. Each instruction has additional useage_notes and effects keys that are passed on to the AI prompt
- With ^^^ we obtain a near-perfect execution of a prompt to create three solutions of varying volumetric ratios. In this case, a math tool isn't needed if the proper phrasing is used.
- Creating a planner repository in docs for sequences that are worth keeping.

## [2025-10-31] how to handle send_problem

**Context**: As handlers become more sophisticated and rely on helper functions, there needs to be some protocol for determining who gets to send messages to host
**Issues**: The send_problem function is being used in helper functions, and it may be more appropriate for these functions to only log information to the machine and let the handler deal with communication
**Action**: Review sidekick functions and consider refactoring.

--- 

## [2025-10-31] Updates

- to_well seems to be working at a satisfactory level of positioning tolerance. 
- homing the device frequently is likely a beneficial approach. It is unclear at what point or after how long the arm loses its positioning
- there is a lot of redundant code for inverse kinematics that should be simplified
- a similarity transform is being used to calibrate wells to robot coordinates
- I don't yet know if the robot coordinates and real world coordinates are identical. 

## [2025-10-19] Fix the try wrapper

**Context**: Attempting to use a wrapper to streamline error catching
**Issues**: Robust error catching seems to require functools, which CircuitPython does not have
**Action**: Evaluate if we need to abandon this approach
**Next Steps**:
- [ ] Try using wrapper._name_ instead of wrapper.__name__ which is read only.
- [ ] try/except the __name__ so it doesn't hang the error catching.

## [2025-10-17] Calibration routine for sidekick _COMPLETE_

**Context**: A standard routine for calibration is needed
**Issue**: Cannot easily store calibration files on CP, but may not make sense for host to manage this
**Action**: SWOT some approaches to calibration and implement.
**Next Steps**:
- [x] Confirm that the motors' world coordinates do not match to real coordinates. _Going from A1 to H12 wells, the tip is about -30 steps in motor 1 and 10 steps in motor 2 from where it should be.
- [x] Confirmed that homing needs to be done somewhat frequently.
- [x] Data for comparing two calibration steps. In the second one, I jogged the motor back and forth many times to see if there is a potential hysteresis issue.

```
Well: A1
  Initial Steps -> (m1: 423, m2: 951)
  Final Steps   -> (m1: 442, m2: 935)
--------------------
Well: H1
  Initial Steps -> (m1: 217, m2: 1185)
  Final Steps   -> (m1: 215, m2: 1168)
--------------------
Well: H12
  Initial Steps -> (m1: 601, m2: 1529)
  Final Steps   -> (m1: 575, m2: 1512)
Well: A1
  Initial Steps -> (m1: 423, m2: 951)
  Final Steps   -> (m1: 444, m2: 935)
--------------------
Well: H1
  Initial Steps -> (m1: 217, m2: 1185)
  Final Steps   -> (m1: 213, m2: 1169)
--------------------
Well: H12
  Initial Steps -> (m1: 601, m2: 1529)
  Final Steps   -> (m1: 574, m2: 1513)
--------------------

(more points using center instead of a pump)
------------------------------------------------------------
Well: A1
  Initial Steps -> (m1: 335, m2: 887)
  Final Steps   -> (m1: 343, m2: 889)
--------------------
Well: A6
  Initial Steps -> (m1: 712, m2: 1130)
  Final Steps   -> (m1: 717, m2: 1137)
--------------------
Well: A12
  Initial Steps -> (m1: 987, m2: 1486)
  Final Steps   -> (m1: 965, m2: 1480)
--------------------
Well: D1
  Initial Steps -> (m1: 276, m2: 1006)
  Final Steps   -> (m1: 278, m2: 1006)
--------------------
Well: D6
  Initial Steps -> (m1: 563, m2: 1181)
  Final Steps   -> (m1: 561, m2: 1185)
--------------------
Well: D12
  Initial Steps -> (m1: 778, m2: 1462)
  Final Steps   -> (m1: 762, m2: 1460)
--------------------
Well: H1
  Initial Steps -> (m1: 131, m2: 1178)
  Final Steps   -> (m1: 125, m2: 1182)
--------------------
Well: H6
  Initial Steps -> (m1: 363, m2: 1294)
  Final Steps   -> (m1: 357, m2: 1298)
--------------------
Well: H12
  Initial Steps -> (m1: 518, m2: 1516)
  Final Steps   -> (m1: 492, m2: 1526)
--------------------


```

---

## [2025-10-10] Improve GUI experience

**Context**: The MVC app can be improved
**Issue**: Among other things, the commands are not in alphabetical order
**Action**: Have the Available commands operation alphabetize the commands

---

## [2025-10-08] Rename and organize host_app _COMPLETE_

**Context**: The three main structures of the program are messaging (communicate), devices (firmware) and the host (host_app).
**Issue**: Renaming host_app to host and reorganizing to have utilities, gui, core, etc may be helpful for future proofing
**Action**: move host_utilities in here, check that all dependencies are updated
- [X] Rename host_app to host
- [X] Deal with all the crap that appears because of ^^^
- [X] test updates

---

## [2025-10-08] Assumptions should be included in documentation

**Context**: Hardware/software design assumptions need to be clear for new developers
**Issue**: Is it obvious that microcontrollers must use CP at this point?
**Action**: Include in documentation some clear assumptions
**Next Steps**:
- [ ] Write an executive summary for the design protocols with asusumptions
- [ ] Identify what belongs in a _Getting Started_ section.

---

## [2025-10-07] Deprecated scanning colorimeter script

**Context**: Reviewing the code base, we see old scripts that use deprecated approaches
**Issue**: `scanning_colorimeter.py` creates its own postman, which was acceptable prior to creation of the DeviceManager
**Action**: Rewrite this script as a demonstration with current infrastructure
**Next Steps**
- [ ] Update `host.md` in the documention upon completion of this task

---

## [2025-10-07] Host testing with fake device

**Context**: Development when I don't have access to the devices
**Issue**: I'd like to try out some AI orchestration without needing access to the actual devices
**Action**: Create a fakelab - Use our understanding of the code to access commands and generate fake data
**Next Steps**
- [ ] step 1
- [ ] step 2

---

## [2025-10-07] Homing should use sequencer

**Context**: Homing state of sidekick has not bee updated since introduction of sequencing
**Issue**: Results in non-standard code
**Action**: Refactoring
**Next Steps**
- [ ] step 1
- [ ] step 2

---

