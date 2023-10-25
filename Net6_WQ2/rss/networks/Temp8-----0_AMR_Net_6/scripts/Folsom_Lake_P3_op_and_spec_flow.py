from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants


#######################################################################################################
# Get the WQSubdomain object from the reservoir using the current rule
def getReservoirWQSubdomain(currentRule, network):
	resOp = currentRule.getController().getReservoirOp()
	res = resOp.getReservoirElement()
	wqRun = network.getRssRun().getWQRun()
	rssWQGeometry = wqRun.getRssWQGeometry()
	resWQGeoSubdom = rssWQGeometry.getSubdomForRSSElemId(res.getIndex())
	return resWQGeoSubdom


#######################################################################################################
def initRuleScript(currentRule, network):

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
		for k in range(nLevels):
			if k > 0:  # don't adjust lowest level because of penstock intakes
				elevs[k] += offset
			isRect.append(True)
			heights.append(0.)
			widths.append(0.)
			diameters.append(0.)
		resOp = currentRule.getController().getReservoirOp()
		releaseElemId = resOp.getWQCDReleaseElemId(currentRule)
		engineAdapter = wqRun.getWqEngineAdapter()
		resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
		irtn = engineAdapter.reallocateWQControlDeviceData(resWQGeoSubdom, releaseElemId, nLevels, elevs, isRect, heights, widths, diameters)
		if irtn != 0:
			return Constants.FALSE
		else:
			return Constants.TRUE


#######################################################################################################
def runRuleScript(currentRule, network, currentRuntimestep):

	flowGlobalVarName = "P3_specified_flow"
	elevGlobalVarName = "P3_shutter_elev"
	
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
		globVar = network.getGlobalVariable(elevGlobalVarName)
		if not globVar:
			raise NameError("Global variable: " + elevGlobalVarName + " not found.")
		elevVal = globVar.getCurrentValue(currentRuntimestep)
		if not isValidValue(elevVal):
			raise ValueError("Global variable: " + elevGlobalVarName + " has invalid value " +
			                 str(elevVal) + " for time step: " + str(currentRuntimestep.step))
		setTCDoperation(currentRule, flowVal, elevVal)

	opValue = OpValue()
	opValue.init(OpRule.RULETYPE_SPEC, flowVal)

	return opValue


#######################################################################################################
# Check whether a value is valid
def isValidValue(value):
	if value == Constants.UNDEFINED_DOUBLE:
		return False
	elif value < -0.000001:
		return False
	else:
		return True


#######################################################################################################
# Set the TCD operation
def setTCDoperation(currentRule, flowVal, elevVal):

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
	for j, portElev in enumerate(portElevs):
		if abs(elevVal - portElev) < 0.01:
			tcdFlows[j] += remainingFlow
			setFlow = True
	if not setFlow:
		tcdFlows[0] += remainingFlow  # set at lowest layer (flowVal *should* be zero)
	
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return
