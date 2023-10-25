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

	globalVarName = "P3_flow_calib"
	
	globVar = network.getGlobalVariable(globalVarName)
	if not globVar:
		raise NameError("Global variable: " + globalVarName + " not found.")
	flowVal = globVar.getCurrentValue(currentRuntimestep)
	
	if not isValidValue(flowVal):
		raise ValueError("Global variable: " + globalVarName + " has invalid value " +
		                 str(flowVal) + " for time step: " + str(currentRuntimestep.step))

	globalVarName = "P3_active_port_calib"
	
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
	if not isValidValue(resElev):  # try previous time step value
		prevRuntimestep = RunTimeStep(currentRuntimestep)
		prevRuntimestep.setStep(currentRuntimestep.getPrevStep())
		resElev = res.getStorageFunction().getElevation(prevRuntimestep)
	if not isValidValue(resElev):
		raise ValueError("Invalid value: " + str(resElev) + 
		                 " for reservoir elevation for time step: " + str(currentRuntimestep.step))

	setTCDoperation(currentRule, flowVal, int(portVal), resElev)

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
def setTCDoperation(currentRule, flowVal, portVal, resElev):

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
	for j in reversed(range(portVal)):
		if resElev > inletElevs[j]:
			newPortVal = j
			break
	tcdFlows[newPortVal] = flowVal
	
	resOp.setWQControlDeviceFlowRatios(tcdFlows, currentRule, flowVal)

	return
 
