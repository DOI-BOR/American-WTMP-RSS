from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants


def getReservoirWQSubdomain(currentRule, network):
	"""Look up the Water Quality subdomain geometry associated with a rule's reservoir.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object, used to reach the controller and
		its reservoir element.
	network : object
		HEC-ResSim network object, used to reach the current run's Water
		Quality run and geometry.

	Returns
	-------
	object
		The WQ subdomain geometry object corresponding to the reservoir
		element controlled by ``currentRule``.

	Notes
	-----
	Resolution path is rule -> reservoir operation -> reservoir element ->
	RSS element index -> matching WQ subdomain in the run's WQ geometry.
	Used both by initRuleScript (for the one-time port-elevation
	reallocation) and indirectly informs setTCDoperation's port-matching
	logic via the elevations configured during initialization.
	"""
	# Walk from the rule to its controlled reservoir, then from the current
	# run's WQ geometry to the specific subdomain matching that reservoir's
	# RSS element index.
	resOp = currentRule.getController().getReservoirOp()
	res = resOp.getReservoirElement()
	wqRun = network.getRssRun().getWQRun()
	rssWQGeometry = wqRun.getRssWQGeometry()
	resWQGeoSubdom = rssWQGeometry.getSubdomForRSSElemId(res.getIndex())
	return resWQGeoSubdom


def initRuleScript(currentRule, network):
	"""Initialize this scripted rule: disable it if WQ is off, else raise TCD port elevations.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being initialized.
	network : object
		HEC-ResSim network object, used to query the current run's Water
		Quality (WQ) configuration and reallocate control-device geometry.

	Returns
	-------
	int
		``Constants.TRUE`` if WQ is disabled (rule force-disabled) or if
		the port-elevation reallocation succeeds; ``Constants.FALSE`` if
		the reallocation call reports a nonzero return code.

	Notes
	-----
	Unlike the simpler EID/Muni rule scripts, this initialization does more
	than toggle the rule on/off: when WQ is running, it performs a
	one-time reallocation of the TCD (temperature control device) port
	elevations, raising every port except the lowest by a fixed offset
	(8.9 ft). The lowest port (307 ft) is deliberately left unmodified
	because it corresponds to penstock intakes rather than an adjustable
	TCD port. This reallocation runs once per compute (at initialization),
	and the shifted elevations become the port elevations that
	setTCDoperation's elevation-matching loop must agree with at runtime;
	if the ``portElevs`` list in setTCDoperation is not updated to reflect
	this same offset, the two functions would be working from inconsistent
	port elevations. This potential mismatch is preserved as-is rather
	than reconciled, since doing so would require changing executable
	values.
	"""

	# Handle case where rule is active or disabled but WQ is not being run
	wqRun = network.getRssRun().getWQRun()
	if not wqRun:
		currentRule.setEvalRule(False)
		network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
			" references Water Quality which is disabled for this simulation.")
		return Constants.TRUE
	else:
		# Reallocate WQCD geometry in WQ Engine to move withdrawal centerline higher
		offset = 8.9
		elevs = [307., 323., 336., 349., 362., 401.]
		nLevels = len(elevs)
		isRect = []
		heights = []
		widths = []
		diameters = []
		# Raise every port except the lowest (penstock-intake level) by the
		# fixed offset; the other geometry lists are populated in lockstep
		# as simple point-withdrawal placeholders (non-rectangular opening
		# with zero height/width/diameter), one entry per port.
		for k in range(nLevels):
			if k > 0:  # don't adjust lowest level because of penstock intakes
				elevs[k] += offset
			isRect.append(True)
			heights.append(0.)
			widths.append(0.)
			diameters.append(0.)
		# Push the adjusted port geometry to the WQ engine for this
		# reservoir's control device, once, at initialization.
		resOp = currentRule.getController().getReservoirOp()
		releaseElemId = resOp.getWQCDReleaseElemId(currentRule)
		engineAdapter = wqRun.getWqEngineAdapter()
		resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
		irtn = engineAdapter.reallocateWQControlDeviceData(resWQGeoSubdom, releaseElemId, nLevels, elevs, isRect, heights, widths, diameters)
		if irtn != 0:
			return Constants.FALSE
		else:
			return Constants.TRUE


def runRuleScript(currentRule, network, currentRuntimestep):
	"""Evaluate the P1 TCD flow/shutter-elevation rule for the current time step.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being evaluated.
	network : object
		HEC-ResSim network object, used to look up global variables for the
		specified flow and shutter elevation.
	currentRuntimestep : object
		Current simulation time step object, passed to global-variable
		lookups and used in error messages.

	Returns
	-------
	OpValue
		A flow-specification operation value (``OpRule.RULETYPE_SPEC``)
		set to the current P1-specified flow.

	Raises
	------
	NameError
		If the "P1_specified_flow" or (when the rule is actively
		evaluated) "P1_shutter_elev" global variable is not defined in the
		network.
	ValueError
		If either global variable's current value is undefined or negative
		(beyond a small numerical tolerance).

	Notes
	-----
	As with the other TCD rule scripts in this project, the WQ-side TCD
	port operation (setTCDoperation) is only applied when
	``computeIter > 1``, since on the 0th iteration Water Quality has not
	yet run for this time step. Regardless of iteration, the function
	always returns a RULETYPE_SPEC OpValue built from the specified flow.
	Unlike the Muni rule script, both global-variable validity checks here
	correctly test their own corresponding values (no flowVal/elevVal
	mix-up).
	"""

	flowGlobalVarName = "P1_specified_flow"
	elevGlobalVarName = "P1_shutter_elev"
	
	# Look up the specified P1 flow; required every time step regardless of
	# compute iteration, since it is returned below.
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
		# Look up the specified shutter elevation and validate it before
		# applying the TCD port operation.
		globVar = network.getGlobalVariable(elevGlobalVarName)
		if not globVar:
			raise NameError("Global variable: " + elevGlobalVarName + " not found.")
		elevVal = globVar.getCurrentValue(currentRuntimestep)
		if not isValidValue(elevVal):
			raise ValueError("Global variable: " + elevGlobalVarName + " has invalid value " +
			                 str(elevVal) + " for time step: " + str(currentRuntimestep.step))
		setTCDoperation(currentRule, flowVal, elevVal)

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
		Value to validate, typically a global-variable flow or elevation
		reading.

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


def setTCDoperation(currentRule, flowVal, elevVal):
	"""Split the specified flow between TCD leakage and the matching shutter port.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object, used to reach the controller and
		its associated reservoir operation.
	flowVal : float
		Total specified flow to distribute across the TCD's 6 inlet
		levels.
	elevVal : float
		Specified shutter elevation; matched (within tolerance) against the
		TCD's known port elevations to decide which port receives the
		non-leakage portion of the flow.

	Returns
	-------
	None

	Notes
	-----
	The TCD is modeled with 6 inlet levels. 35% of the total flow is always
	assigned to the lowest level (index 0) as leakage, regardless of the
	requested shutter elevation. The remaining 65% is assigned to whichever
	port's elevation matches ``elevVal`` within a 0.01 tolerance; if none
	matches, that remaining flow is also added to the lowest level, under
	the assumption (stated in the original inline comment but not verified
	in code) that ``flowVal`` should be zero in that situation -- i.e. an
	unmatched elevation is expected to coincide with no flow being
	specified at all, but this is not actually checked or enforced here.
	The ``portElevs`` list below must stay consistent with whatever port
	elevations are active in the WQ engine; see the note in initRuleScript
	regarding the one-time elevation offset applied there.
	"""

	# Fill TCD inlet flow array
	tcdFlows = []
	nInletLevels = 6
	# Initialize
	for j in range(nInletLevels):
		tcdFlows.append(0.0)
	# Leakage
	tcdFlows[0] = 0.35 * flowVal
	remainingFlow = 0.65 * flowVal
	# Set based on port elevation
	portElevs = [307., 323., 336., 349., 362., 401.]
	setFlow = False
	# Find the port whose elevation matches the specified shutter elevation
	# (within a small tolerance) and route the remaining 65% of flow there.
	for j, portElev in enumerate(portElevs):
		if abs(elevVal - portElev) < 0.01:
			tcdFlows[j] += remainingFlow
			setFlow = True
	if not setFlow:
		tcdFlows[0] += remainingFlow  # set at lowest layer (flowVal *should* be zero)
	
	# Push the completed 6-element flow-ratio array to the reservoir
	# operation per its expected calling convention.
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return