from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants


#######################################################################################################
def initRuleScript(currentRule, network):

	# Handle case where rule is active or disabled but WQ is not being run
	wqRun = network.getRssRun().getWQRun()
	if not wqRun:
		currentRule.setEvalRule(False)
		network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
			" references Water Quality which is disabled for this simulation.")
	return Constants.TRUE


#######################################################################################################
def runRuleScript(currentRule, network, currentRuntimestep):

	flowGlobalVarName = "Muni_specified_flow"
	elevGlobalVarName = "Muni_intake_elev"
	
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
		if elevVal == Constants.UNDEFINED_DOUBLE:
			elevVal = -1.  # Need to handle missing data because no elev time series data before 2004
		setMuniOperation(currentRule, flowVal, elevVal)

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
# Get the WQSubdomain object from the reservoir using the current rule
def getReservoirWQSubdomain(currentRule, network):
	resOp = currentRule.getController().getReservoirOp()
	res = resOp.getReservoirElement()
	wqRun = network.getRssRun().getWQRun()
	rssWQGeometry = wqRun.getRssWQGeometry()
	resWQGeoSubdom = rssWQGeometry.getSubdomForRSSElemId(res.getIndex())
	return resWQGeoSubdom


#######################################################################################################
# Set the TCD operation
def setMuniOperation(currentRule, flowVal, elevVal, resElev):

	# Fill TCD inlet flow array - only 1 inlet
	tcdFlows = []
	tcdFlows.append(flowVal)
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	# Change withdrawal elevation based on elevation time series
	if elevVal > 0:
		targetElev = elevVal
		
	else:
		# Need to choose elevation based on state of reservoir stratification
		wqRun = network.getRssRun().getWQRun()
		engineAdapter = wqRun.getWqEngineAdapter()
		resWQGeoSubdom = getReservoirWQSubdomain(currentRule, network)
		resLayerElevs = resWQGeoSubdom.getResVerticalLayerBoundaries()
		numLayers = len(resLayerElevs)-1
		layerTemps = engineAdapter.getReservoirLayerTemperatures(resWQGeoSubdom)

		# Find correct elevation - use highest possible
		targetTemp = 18.  # deg C
		maxElev = 401.
		minElev = 331.5  # how to know when allowed to go to 317?
		targetLayer = 0
		for k in reversed(range(numLayers)):
			layerBotElev = resLayerElevs[k]
			layerTemp = layerTemps[k]
			if ((layerBotElev < maxElev and layerBotElev < resElev and layerTemp < targetTemp)
				or layerBotElev < minElev):
				targetLayer = k
				break
		targetElev = resLayerElevs[targetLayer]

	# Reallocate WQCD geometry in WQ Engine
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

	return
