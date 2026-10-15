from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants


def initRuleScript(currentRule, network):
	"""Initialize this scripted rule, disabling it if Water Quality is not running.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being initialized.
	network : object
		HEC-ResSim network object, used to query the current run's Water
		Quality (WQ) configuration.

	Returns
	-------
	int
		``Constants.TRUE``, unconditionally.

	Notes
	-----
	This rule depends on Water Quality results (the EID flow decision is a
	WQ-driven operation). If WQ is not enabled for the current run, the
	rule is force-disabled so it never attempts to reference WQ data that
	will not exist for this simulation.
	"""

	# This rule depends on WQ results, so force it off (and warn) if the
	# current run does not have Water Quality enabled, regardless of
	# whether the rule was otherwise active or already disabled.
	wqRun = network.getRssRun().getWQRun()
	if not wqRun:
		currentRule.setEvalRule(False)
		network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
			" references Water Quality which is disabled for this simulation.")
	return Constants.TRUE


def runRuleScript(currentRule, network, currentRuntimestep):
	"""Evaluate the EID flow-specification rule for the current time step.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being evaluated.
	network : object
		HEC-ResSim network object, used to look up the global variable
		holding the externally specified EID flow.
	currentRuntimestep : object
		Current simulation time step object, passed to the global
		variable's value lookup and used in error messages.

	Returns
	-------
	OpValue
		A flow-specification operation value (``OpRule.RULETYPE_SPEC``)
		set to the current EID-specified flow.

	Raises
	------
	NameError
		If the "EID_specified_flow" global variable is not defined in the
		network.
	ValueError
		If the global variable's current value is undefined or negative
		(beyond a small numerical tolerance).

	Notes
	-----
	The TCD (temperature control device) operation is only pushed to the
	reservoir controller when ``computeIter > 1``; on the 0th iteration,
	only local reservoir decisions are being evaluated and Water Quality
	has not yet run for this time step, so applying the EID operation then
	would act on stale or unavailable WQ information. Regardless of
	iteration, the function still returns a RULETYPE_SPEC OpValue reflecting
	the current flow value.
	"""

	flowGlobalVarName = "EID_specified_flow"
	
	# Look up the externally specified EID flow; this is required every
	# time step regardless of compute iteration, since it is returned below.
	globVar = network.getGlobalVariable(flowGlobalVarName)
	if not globVar:
		raise NameError("Global variable: " + flowGlobalVarName + " not found.")
	flowVal = globVar.getCurrentValue(currentRuntimestep)
	if not isValidValue(flowVal):
		raise ValueError("Global variable: " + flowGlobalVarName + " has invalid value " +
		                 str(flowVal) + " for time step: " + str(currentRuntimestep.step))

	# Only evaluate WQ part of script running WQ and computer iteration > 0
	#  (On 0th iteration, only local res decisions being evaluated and WQ is not being run yet)
	computeIter = currentRule.getComputeIteration()
	evalRule = currentRule.getEvalRule() and (computeIter > 1)
	if evalRule:
		setEIDoperation(currentRule, flowVal)

	# Regardless of whether the WQ-side TCD operation above was applied,
	# the rule always returns a flow specification built from flowVal.
	opValue = OpValue()
	opValue.init(OpRule.RULETYPE_SPEC, flowVal)

	return opValue


def isValidValue(value):
	"""Check whether a numeric value is defined and non-negative.

	Parameters
	----------
	value : float
		Value to validate, typically a global-variable flow reading.

	Returns
	-------
	bool
		False if ``value`` equals ``Constants.UNDEFINED_DOUBLE`` or is less
		than approximately zero (tolerance of -0.000001 to allow for
		floating-point noise around zero); True otherwise.
	"""
	if value == Constants.UNDEFINED_DOUBLE:
		return False
	elif value < -0.000001:
		return False
	else:
		return True


def setEIDoperation(currentRule, flowVal):
	"""Apply the specified EID flow to the reservoir's TCD inlet-level controls.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object, used to reach the controller and
		its associated reservoir operation.
	flowVal : float
		EID-specified flow value to assign to the lowest TCD inlet level.

	Returns
	-------
	None

	Notes
	-----
	The temperature control device (TCD) is modeled with 3 inlet levels;
	only the lowest level (index 0, corresponding to elevation 325) is set
	to the EID flow, while the other two levels remain at 0.0.
	"""

	# This TCD has 3 inlet levels; only the lowest (index 0, elevation 325)
	# ever carries flow for this rule, so the array starts all-zero and
	# only the first element is overwritten below.
	tcdFlows = []
	nInletLevels = 3
	# Initialize
	for j in range(nInletLevels):
		tcdFlows.append(0.0)
	# Always set at lowest level (325)
	tcdFlows[0] = flowVal
	
	# Push the full 3-element ratio array, plus the raw flow value, to the
	# reservoir operation per its expected calling convention.
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return