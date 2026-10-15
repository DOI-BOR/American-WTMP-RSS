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
	This rule depends on Water Quality results (the municipal withdrawal
	elevation/temperature logic in runRuleScript/setMuniOperation is
	WQ-driven). If WQ is not enabled for the current run, the rule is
	force-disabled so it never attempts to reference WQ data that will not
	exist for this simulation.
	"""

	# This rule depends on WQ results, so force it off (and warn) if the
	# current run does not have Water Quality enabled.
	wqRun = network.getRssRun().getWQRun()
	if not wqRun:
		currentRule.setEvalRule(False)
		network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
			" references Water Quality which is disabled for this simulation.")
	return Constants.TRUE


def runRuleScript(currentRule, network, currentRuntimestep):
	"""Evaluate the municipal-withdrawal flow/elevation rule for the current time step.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being evaluated.
	network : object
		HEC-ResSim network object, used to look up global variables for the
		specified municipal flow and intake elevation.
	currentRuntimestep : object
		Current simulation time step object, passed to global-variable
		lookups, elevation lookups, and used in error messages.

	Returns
	-------
	OpValue
		A flow-specification operation value (``OpRule.RULETYPE_SPEC``)
		set to the current municipal-specified flow.

	Raises
	------
	NameError
		If the "Muni_specified_flow" or (when the rule is actively
		evaluated) "Muni_intake_elev" global variable is not defined in the
		network.
	ValueError
		If the specified flow is undefined/negative, or if the reservoir
		elevation cannot be resolved as valid at either the current or
		previous time step.

	Notes
	-----
	The WQ-driven part of this rule (elevation lookup and the call to
	setMuniOperation) is only evaluated when ``computeIter > 1``, since on
	the 0th iteration only local reservoir decisions are being made and
	Water Quality has not yet run for this time step. Regardless of
	iteration, the function always returns a RULETYPE_SPEC OpValue built
	from the specified flow. Reservoir elevation is looked up at the
	current time step and, if not yet valid, falls back to the previous
	time step before raising an error -- this accommodates cases where the
	current step's elevation hasn't been computed yet this iteration.

	Known quirk: the validity check performed right after reading
	``elevVal`` tests ``isValidValue(flowVal)`` rather than
	``isValidValue(elevVal)``. Given the accompanying comment references
	missing elevation data before 2004, this looks like an unintentional
	reuse of the flow variable rather than the intended elevation check.
	It is preserved exactly rather than corrected, per documentation
	policy. ``RunTimeStep`` is also referenced without a visible import in
	this file and is assumed to be available in the HEC-ResSim scripting
	namespace at runtime.
	"""

	flowGlobalVarName = "Muni_specified_flow"
	elevGlobalVarName = "Muni_intake_elev"
	
	# Look up the required municipal flow global variable; this is always
	# needed, regardless of compute iteration, since it is returned below.
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
		# Look up the intake-elevation global variable. Note: the validity
		# check immediately below tests flowVal again rather than elevVal;
		# given the accompanying comment references missing elevation data
		# before 2004, this looks like an unintentional reuse of the flow
		# variable rather than the intended elevation check. Preserved
		# exactly rather than corrected.
		globVar = network.getGlobalVariable(elevGlobalVarName)
		if not globVar:
			raise NameError("Global variable: " + elevGlobalVarName + " not found.")
		elevVal = globVar.getCurrentValue(currentRuntimestep)
		if not isValidValue(flowVal):
			elevVal = -1.  # Need to handle missing data because no elev time series data before 2004
		
		# Get reservoir elevation
		resOp = currentRule.getController().getReservoirOp()
		res = resOp.getReservoirElement()
		resElev = res.getStorageFunction().getElevation(currentRuntimestep)
		# Fall back to the previous time step's elevation if the current
		# one is not yet valid (e.g. not computed yet this iteration);
		# RunTimeStep is assumed available in the scripting namespace,
		# since it is not imported in this file.
		if not isValidValue(resElev):  # try previous time step value
			prevRuntimestep = RunTimeStep(currentRuntimestep)
			prevRuntimestep.setStep(currentRuntimestep.getPrevStep())
			resElev = res.getStorageFunction().getElevation(prevRuntimestep)
		if not isValidValue(resElev):
			raise ValueError("Invalid value: " + str(resElev) + 
			                 " for reservoir elevation for time step: " + str(currentRuntimestep.step))
		
		# Apply the flow and resolve/reallocate the intake elevation only
		# once WQ is actually running this iteration (see evalRule above).
		setMuniOperation(currentRule, flowVal, elevVal, resElev)

	# Regardless of whether the WQ-side operation above was applied, the
	# rule always returns a flow specification built from flowVal.
	opValue = OpValue()
	opValue.init(OpRule.RULETYPE_SPEC, flowVal)

	return opValue


def isValidValue(value):
	"""Check whether a numeric value is defined and non-negative.

	Parameters
	----------
	value : float
		Value to validate, typically a global-variable or elevation
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
	Used by setMuniOperation to reach both the vertical layer geometry and
	the WQ engine adapter needed to reallocate the control device.
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


def setMuniOperation(currentRule, flowVal, elevVal, resElev):
	"""Apply the municipal withdrawal flow and resolve/reallocate its intake elevation.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object, used to reach the controller,
		reservoir operation, and WQ control-device release element.
	flowVal : float
		Municipal withdrawal flow to assign to the single TCD inlet.
	elevVal : float
		Specified intake elevation from the "Muni_intake_elev" time
		series, or a sentinel (-1.) when no valid time series value is
		available for the current time step.
	resElev : float
		Current (or previous-time-step fallback) reservoir water-surface
		elevation, used both to cap a specified intake elevation and as an
		upper bound when inferring an elevation from stratification.

	Returns
	-------
	int or None
		``Constants.FALSE`` if the WQ engine's control-device reallocation
		call reports a nonzero return code, ``Constants.TRUE`` on success.
		The function has an unreachable trailing ``return`` after the
		``if/else`` that already returns in both branches; this dead code
		is preserved as-is rather than removed.

	Notes
	-----
	The TCD here has a single inlet (unlike the EID rule's 3-level TCD),
	so ``tcdFlows`` is a one-element list set directly to ``flowVal``.

	Target elevation is resolved one of two ways:

	- If ``elevVal`` is a valid positive value (an explicit time-series
	  specification is available), the target elevation is the lesser of
	  ``elevVal`` and the current reservoir elevation ``resElev`` -- i.e.
	  the specified intake depth is honored unless it would be above the
	  current pool surface.
	- Otherwise, the target elevation is inferred from the reservoir's
	  vertical temperature stratification: starting from the top layer and
	  working downward, the first (highest) layer whose bottom elevation is
	  below ``maxElev``, below the current reservoir elevation, and whose
	  temperature is below the 65 deg F (18.3333 deg C) target is selected;
	  failing that, the search falls back to the first layer entirely below
	  a fixed minimum elevation (``minElev = 331.5``). The inline comment
	  "how to know when allowed to go to 317?" reflects unresolved
	  developer uncertainty about this lower bound and is preserved as-is.

	The resolved single elevation is submitted to the WQ engine via
	``reallocateWQControlDeviceData``, describing the control device as a
	single point withdrawal (height/width/diameter left at 0) rather than
	a real multi-opening or non-rectangular structure.
	"""

	# This TCD has a single inlet (unlike the EID rule's 3-level TCD), so
	# the flow-ratio array is just the one specified flow value.
	tcdFlows = []
	tcdFlows.append(flowVal)
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	# Change withdrawal elevation based on elevation time series
	wqRun = network.getRssRun().getWQRun()
	engineAdapter = wqRun.getWqEngineAdapter()
	resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
	if elevVal > 0:
		# An explicit intake elevation was specified in the time series;
		# honor it, but never let it exceed the current reservoir surface.
		targetElev = min([elevVal, resElev])
		
	else:
		# Need to choose elevation based on state of reservoir stratification
		resLayerElevs = resWQGeoSubdom.getResVerticalLayerBoundaries()
		numLayers = len(resLayerElevs)-1
		layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)

		# Find correct elevation - use highest possible
		targetTemp = 18.3333  # deg C (65 deg F)
		maxElev = 401.
		minElev = 331.5  # how to know when allowed to go to 317?
		targetLayer = 0
		# Scan layers top-down (reversed index order) so the first match
		# found is the highest (shallowest) usable layer. A layer qualifies
		# if its bottom is below the surface, below the hard ceiling
		# maxElev, and cool enough to meet targetTemp; failing that, the
		# scan still stops once it reaches a layer below the hard floor
		# minElev, taking that layer regardless of temperature.
		for k in reversed(range(numLayers)):
			layerBotElev = resLayerElevs[k]
			layerTemp = layerTemps[k]
			if ((layerBotElev < maxElev and layerBotElev < resElev and layerTemp < targetTemp)
				or layerBotElev < minElev):
				targetLayer = k
				break
		targetElev = resLayerElevs[targetLayer]

	# Describe the control device as a single non-rectangular-opening point
	# withdrawal at the resolved elevation (height/width/diameter left at
	# 0, consistent with a simple point intake rather than a real opening),
	# and push that geometry to the WQ engine.
	elevs = [targetElev]
	isRect = [True]
	heights = [0.]
	widths = [0.]
	diameters = [0.]
	releaseElemId = resOp.getWQCDReleaseElemId(currentRule)
	irtn = engineAdapter.reallocateWQControlDeviceData(resWQGeoSubdom, releaseElemId, len(elevs), elevs, isRect, heights, widths, diameters)
	if irtn != 0:
		return Constants.FALSE
	else:
		return Constants.TRUE

	# Unreachable: both branches above already return.
	return