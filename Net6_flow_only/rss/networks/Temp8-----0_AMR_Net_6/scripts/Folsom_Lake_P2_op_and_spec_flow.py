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

	flowGlobalVarName = "P2_specified_flow"
	elevGlobalVarName = "P2_shutter_elev"
	
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
	if not value:
		return False
	elif value == Constants.UNDEFINED_DOUBLE:
		return False
	elif value < 0.:
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
	# Set based on portVal
	portElevs = [307., 323., 336., 349., 362., 401.]
	setFlow = False
	for j, portElev in enumerate(portElevs):
		if abs(elevVal - portElev) < 0.01:
			tcdFlows[j] = flowVal
			setFlow = True
	if not setFlow:
		tcdFlows[0] = flowVal  # set at lowest layer (flowVal *should* be zero)
	
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return
