# required imports to create the OpValue return object.
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

#
# initialization function. optional.
#
# set up tables and other things that only need to be performed once during
# the compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
#
#
def initRuleScript(currentRule, network):
	# return Constants.TRUE if the initialization is successful
	# and Constants.FALSE if it failed.  Returning Constants.FALSE
	# will halt the compute.
	return Constants.TRUE


# runRuleScript() is the entry point that is called during the
# compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
# currentRuntimestep is the current Run Time Step
def runRuleScript(currentRule, network, currentRuntimestep):

	globalVarName = "P2_flow_calib"
	
	globVar = network.getGlobalVariable(globalVarName)
	if not globVar:
		raise NameError("Global variable: " + globalVarName + " not found.")
	flowVal = globVar.getCurrentValue(currentRuntimestep)
	
	if not isValidValue(flowVal):
		raise ValueError("Global variable: " + globalVarName + " has invalid value " +
		                 str(flowVal) + " for time step: " + str(currentRuntimestep.step))

	globalVarName = "P2_active_port_calib"
	
	globVar = network.getGlobalVariable(globalVarName)
	if not globVar:
		raise NameError("Global variable: " + globalVarName + " not found.")
	portVal = globVar.getCurrentValue(currentRuntimestep)
	if not isValidValue(portVal):
		raise ValueError("Global variable: " + globalVarName + " has invalid value " +
		                 str(portVal) + " for time step: " + str(currentRuntimestep.step))

	setTCDoperation(currentRule, flowVal, int(portVal))

	# create new Operation Value (OpValue) to return
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
def setTCDoperation(currentRule, flowVal, portVal):

	# Fill TCD inlet flow array
	tcdFlows = []
	nInletLevels = 4
	# Initialize
	for j in range(nInletLevels):
		tcdFlows.append(0.0)
	# Set based on portVal
	tcdFlows[portVal-1] = flowVal
	
	resOp = currentRule.getController().getReservoirOp()
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return
