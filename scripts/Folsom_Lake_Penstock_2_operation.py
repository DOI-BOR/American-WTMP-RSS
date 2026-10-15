# required imports to create the OpValue return object.
from hec.model import RunTimeStep
from hec.rss.model import OpController
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.rss.model import ReservoirElement
from hec.rss.plugins.waterquality.model import RssWQGeometry
from hec.rss.wq.model import WQRun
from hec.script import Constants
from hec.wqenginecore import WQEngineAdapter
from hec.wqenginecore import WQResHydro
from hec.wqenginecore.geometry import SubDomain
from hec.wqenginecore.geometry import WQControlDevice
from java.util import Vector

def initRuleScript(currentRule, network):
	"""Perform one-time setup for this scripted rule before the compute runs.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object that holds this script.
	network : object
		HEC-ResSim network object for the current compute.

	Returns
	-------
	int
		``Constants.TRUE`` if initialization succeeded, or
		``Constants.FALSE`` if it failed. Returning ``Constants.FALSE``
		halts the compute.

	Notes
	-----
	Unlike the P1/P2/P3 TCD rule scripts in this project (which perform a
	one-time port-elevation reallocation here), this calibration variant
	has no such setup and simply signals successful initialization. This
	file is structurally and byte-identical to the P1 calibration rule
	script, differing only in the global variable names used in
	runRuleScript.
	"""
	# return Constants.TRUE if the initialization is successful
	# and Constants.FALSE if it failed.  Returning Constants.FALSE
	# will halt the compute.
	return Constants.TRUE


def runRuleScript(currentRule, network, currentRuntimestep):
	"""Evaluate the P2 calibration flow/port rule for the current time step.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being evaluated.
	network : object
		HEC-ResSim network object, used to look up global variables for the
		specified flow and target active port index.
	currentRuntimestep : object
		Current simulation time step object, passed to global-variable
		lookups, elevation lookups, and used in error messages.

	Returns
	-------
	OpValue
		A flow-specification operation value (``OpRule.RULETYPE_SPEC``)
		set to the current P2 calibration flow.

	Raises
	------
	NameError
		If "P2_flow_calib" or "P2_active_port_calib" is not defined as a
		global variable in the network.
	ValueError
		If the flow or port global variable's current value is invalid, or
		if reservoir elevation cannot be resolved as valid at either the
		current or previous time step.

	Notes
	-----
	Unlike the P1/P2/P3 TCD rule scripts, both the flow and the desired
	port index are read every time step and the TCD operation
	(setTCDoperation) is applied unconditionally -- there is no
	compute-iteration gate (no ``computeIter > 1`` check) and no Water
	Quality on/off check here. Reservoir elevation is looked up at the
	current time step and, if not yet valid, falls back to the previous
	time step before raising an error, matching the pattern used in the
	Muni rule script. This function is identical to the P1 calibration
	rule script's runRuleScript except for the global variable names
	("P2_flow_calib" / "P2_active_port_calib" vs. "P1_flow_calib" /
	"P1_active_port_calib").
	"""

	globalVarName = "P2_flow_calib"
	
	# Look up the calibration flow; required every time step and returned
	# below regardless of the port-selection outcome.
	globVar = network.getGlobalVariable(globalVarName)
	if not globVar:
		raise NameError("Global variable: " + globalVarName + " not found.")
	flowVal = globVar.getCurrentValue(currentRuntimestep)
	
	if not isValidValue(flowVal):
		raise ValueError("Global variable: " + globalVarName + " has invalid value " +
		                 str(flowVal) + " for time step: " + str(currentRuntimestep.step))

	globalVarName = "P2_active_port_calib"
	
	# Look up the target active port index used by setTCDoperation to pick
	# the highest submerged inlet level at or below this index.
	globVar = network.getGlobalVariable(globalVarName)
	if not globVar:
		raise NameError("Global variable: " + globalVarName + " not found.")
	portVal = globVar.getCurrentValue(currentRuntimestep)
	if not isValidValue(portVal):
		raise ValueError("Global variable: " + globalVarName + " has invalid value " +
		                 str(portVal) + " for time step: " + str(currentRuntimestep.step))

	# Get reservoir elevation
	resOp = currentRule.getController().getReservoirOp()
	res = resOp.getReservoirElement()
	resElev = res.getStorageFunction().getElevation(currentRuntimestep)
	# Fall back to the previous time step's elevation if the current one is
	# not yet valid (e.g. not computed yet this iteration).
	if not isValidValue(resElev):  # try previous time step value
		prevRuntimestep = RunTimeStep(currentRuntimestep)
		prevRuntimestep.setStep(currentRuntimestep.getPrevStep())
		resElev = res.getStorageFunction().getElevation(prevRuntimestep)
	if not isValidValue(resElev):
		raise ValueError("Invalid value: " + str(resElev) + 
		                 " for reservoir elevation for time step: " + str(currentRuntimestep.step))

	# Apply the calibration flow at whichever inlet level is actually
	# submerged, given the target port index and current elevation.
	setTCDoperation(currentRule, flowVal, int(portVal), resElev)

	# create new Operation Value (OpValue) to return
	opValue = OpValue()

	opValue.init(OpRule.RULETYPE_SPEC, flowVal)

	return opValue


def isValidValue(value):
	"""Check whether a numeric value is truthy, defined, and non-negative.

	Parameters
	----------
	value : float
		Value to validate, typically a global-variable flow/port reading or
		a reservoir elevation.

	Returns
	-------
	bool
		False if ``value`` is falsy (including 0.0 or None), equals
		``Constants.UNDEFINED_DOUBLE``, or is negative; True otherwise.

	Notes
	-----
	Unlike the ``isValidValue`` used in the EID/Muni/P1-P3 TCD rule
	scripts, this version adds a leading ``if not value:`` check and uses a
	strict ``< 0.`` comparison rather than a small negative tolerance
	(``-0.000001``). Because 0.0 is falsy in Python, this means a flow or
	port value of exactly zero is treated as invalid here, which differs
	from the other scripts' behavior (where exactly 0.0 would pass). This
	difference is preserved as-is rather than reconciled across files. This
	function is byte-identical to the P1 calibration rule script's
	isValidValue.
	"""
	if not value:
		return False
	elif value == Constants.UNDEFINED_DOUBLE:
		return False
	elif value < 0.:
		return False
	else:
		return True


def setTCDoperation(currentRule, flowVal, portVal, resElev):
	"""Apply the calibration flow at the highest submerged inlet at or below a target port.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object, used to reach the controller and
		its associated reservoir operation.
	flowVal : float
		Calibration flow value to assign to the selected TCD inlet level.
	portVal : int
		Target active port index (upper bound, exclusive) to search
		downward from when selecting a submerged inlet level.
	resElev : float
		Current (or previous-time-step fallback) reservoir water-surface
		elevation, used to determine which inlet levels are submerged.

	Returns
	-------
	None

	Notes
	-----
	Unlike the P1/P2/P3 TCD rule scripts' setTCDoperation (which splits
	flow between a fixed leakage port and an elevation-matched port), this
	calibration variant uses a single inlet selection: starting just below
	``portVal`` and searching downward (``reversed(range(portVal))``), it
	picks the first (highest) inlet level whose elevation is below the
	current reservoir elevation, i.e. the highest port that is actually
	submerged at or below the requested port index. If no such level is
	found, ``newPortVal`` remains at its initial value of 0 and the entire
	flow is assigned to inlet level 0. Inlet elevations are queried
	directly from the reservoir operation (``getWQCDInletLevels``) rather
	than hard-coded, unlike the P1/P2/P3 scripts' fixed ``portElevs`` list.
	This function is byte-identical to the P1 calibration rule script's
	setTCDoperation.
	"""

	# Fill TCD inlet flow array
	tcdFlows = []
	resOp = currentRule.getController().getReservoirOp()
	inletElevs = resOp.getWQCDInletLevels(currentRule);
	nInletLevels = len(inletElevs)
	
	# Initialize
	for j in range(nInletLevels):
		tcdFlows.append(0.0)
		
	# Set based on portVal, but check res elevation
	newPortVal = 0
	# Search downward from just below portVal for the highest inlet level
	# that is actually submerged (its elevation is below the current
	# reservoir elevation); stop at the first (highest) match found.
	for j in reversed(range(portVal)):
		if resElev > inletElevs[j]:
			newPortVal = j
			break
	tcdFlows[newPortVal] = flowVal
	
	# Push the completed flow-ratio array to the reservoir operation per
	# its expected calling convention.
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return